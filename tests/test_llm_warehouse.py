"""Warehouse provider + batch classification, all offline (no driver, no network).

Why these matter: someone with no personal API key must be able to point the
pipeline at their warehouse's own LLM function with config alone, get exactly one
answer per message in the right order, and never have prompt text leak into the
SQL statement.
"""
import inspect
from dataclasses import replace

import pytest

from hire_pipeline import pipeline
from hire_pipeline.llm import (
    LLMClient, LLMError, WarehouseClient, build_batch_sql, build_classification_input,
)


# ---- batch interface -------------------------------------------------------
class _CountingClient(LLMClient):
    """Implements only classify(); inherits the default looping classify_batch."""

    def __init__(self):
        self.seen = []

    def classify(self, prompt, text_value, schema, model=None):
        self.seen.append(text_value)
        return {"category": f"cat_{text_value}", "confidence": 0.8}


def test_default_classify_batch_loops_and_preserves_order():
    c = _CountingClient()
    out = c.classify_batch("PROMPT", ["a", "b", "c"], {})
    assert [o["category"] for o in out] == ["cat_a", "cat_b", "cat_c"]
    assert c.seen == ["a", "b", "c"]


def test_classify_is_declared_with_the_model_argument_it_is_called_with():
    """Regression: the declared classify() signature omitted `model` while
    classify_batch() (and Steps 2-3) passed it, so a subclass written to match
    the documented signature raised TypeError on its first batch. The fake above
    happens to accept `model`, which is why the suite stayed green — assert the
    interface itself, not just an implementation of it."""
    params = inspect.signature(LLMClient.classify).parameters
    assert "model" in params, "classify() must accept the model it is called with"
    assert params["model"].default is None


def test_model_is_routed_through_to_classify():
    """The cheap classifier and the stronger judge share one client, so a dropped
    `model` would silently send every escalation to the first-pass model."""
    class Minimal(LLMClient):                      # exactly the documented contract
        def classify(self, prompt, text_value, schema, model=None):
            return {"category": "x", "confidence": 1.0, "used": model}

    out = Minimal().classify_batch("P", ["a", "b"], {}, model="judge-1")
    assert [o["used"] for o in out] == ["judge-1", "judge-1"]


def test_a_custom_client_can_drive_the_whole_pipeline(store, cfg):
    """The documented extension path, end to end: implement classify() and pass
    the instance to run(). Without the llm= parameter this was impossible, so
    llm.py's docstring and the unknown-provider error both pointed nowhere.

    Note the config here has no sql_template and no warehouse URL — an injected
    client must bypass _make_llm entirely rather than being merged with it.
    """
    from helpers import interaction, seed_source

    class Minimal(LLMClient):
        def __init__(self):
            self.calls = 0

        def classify(self, prompt, text_value, schema, model=None):
            self.calls += 1
            return {"category": "correction", "confidence": 0.95, "tone": "angry",
                    "reason": "stub", "other_correct": True, "reason_theme": "t"}

        def complete(self, prompt, model=None):
            return '{"label": "a topic"}'

    seed_source(store, cfg, [
        interaction("i1", "A", 1, user_input="No, that's wrong, I said March 15th."),
        interaction("i2", "A", 2, control="qr_end"),
    ])
    client = Minimal()
    pipeline.run(cfg, store, llm=client)           # must not raise

    assert client.calls > 0, "the injected client was never used"
    assert not store.read(cfg.tables.classified).empty
    assert store.read(cfg.tables.conversation_metrics).shape[0] == 1


def test_every_provider_sends_identical_classification_text():
    """Gold-set scores are only comparable across providers if the wording matches."""
    built = build_classification_input("PROMPT", "some message")
    assert "PROMPT" in built
    assert "some message" in built
    assert "STRICT JSON" in built


# ---- SQL construction (pure, no engine) ------------------------------------
def test_build_batch_sql_databricks_shape():
    sql = build_batch_sql("ai_query('{model}', {input})", "llama-3-3-70b", 3)
    assert "ai_query('llama-3-3-70b', txt)" in sql
    assert "SELECT 0 AS idx, :p0 AS txt" in sql
    assert "UNION ALL SELECT 1, :p1" in sql
    assert "UNION ALL SELECT 2, :p2" in sql
    assert sql.rstrip().endswith("ORDER BY idx")   # ordering must be deterministic


def test_build_batch_sql_snowflake_shape():
    sql = build_batch_sql("SNOWFLAKE.CORTEX.COMPLETE('{model}', {input})", "mistral-large", 1)
    assert "SNOWFLAKE.CORTEX.COMPLETE('mistral-large', txt)" in sql
    assert ":p0" in sql and ":p1" not in sql


def test_prompts_are_bound_parameters_not_interpolated():
    """Few-shot examples contain quotes and braces; they must never reach the SQL."""
    sql = build_batch_sql("ai_query('{model}', {input})", "m", 2)
    assert "TEXT TO CLASSIFY" not in sql        # no prompt text in the statement
    assert sql.count(":p") == 2                 # one bound parameter per row


def test_build_batch_sql_rejects_template_without_input():
    with pytest.raises(ValueError, match="{input}"):
        build_batch_sql("ai_query('{model}')", "m", 1)


def test_build_batch_sql_rejects_empty_batch():
    with pytest.raises(ValueError):
        build_batch_sql("ai_query('{model}', {input})", "m", 0)


# ---- WarehouseClient behaviour (fake execution layer) ----------------------
def _warehouse(responses, **kw):
    """Client with a stubbed _execute so no driver or connection is needed."""
    client = WarehouseClient(url="", classifier_model="cheap", judge_model="strong",
                             sql_template="ai_query('{model}', {input})",
                             engine=object(), **kw)
    calls = []

    def fake_execute(sql, params):
        calls.append((sql, params))
        return responses.pop(0)

    client._execute = fake_execute
    client.calls = calls
    return client


def test_classify_batch_is_one_statement_per_chunk():
    llm = _warehouse([['{"category": "a", "confidence": 0.9}',
                       '{"category": "b", "confidence": 0.7}']])
    out = llm.classify_batch("PROMPT", ["first", "second"], {})
    assert [o["category"] for o in out] == ["a", "b"]
    assert len(llm.calls) == 1                       # the whole point: ONE query
    sql, params = llm.calls[0]
    assert set(params) == {"p0", "p1"}
    assert "first" in params["p0"] and "second" in params["p1"]


def test_batch_size_splits_into_multiple_statements():
    llm = _warehouse([['{"category": "a"}', '{"category": "b"}'], ['{"category": "c"}']],
                     batch_size=2)
    out = llm.classify_batch("PROMPT", ["1", "2", "3"], {})
    assert [o["category"] for o in out] == ["a", "b", "c"]
    assert len(llm.calls) == 2


def test_classifier_and_judge_models_both_usable():
    llm = _warehouse([['{"category": "a"}'], ['{"category": "b"}']])
    llm.classify_batch("P", ["x"], {})                       # default: classifier
    llm.classify_batch("P", ["x"], {}, model="strong")       # explicit: judge
    assert "ai_query('cheap', txt)" in llm.calls[0][0]
    assert "ai_query('strong', txt)" in llm.calls[1][0]


def test_row_count_mismatch_is_reported():
    llm = _warehouse([['{"category": "a"}']])                # one row for two prompts
    with pytest.raises(LLMError, match="1 rows for 2 prompts"):
        llm.classify_batch("PROMPT", ["a", "b"], {})


def test_unparseable_row_falls_back_without_killing_the_batch():
    llm = _warehouse([['not json at all', '{"category": "b", "confidence": 0.7}']])
    out = llm.classify_batch("PROMPT", ["a", "b"], {})
    assert out[0]["category"] == "other" and out[0]["confidence"] == 0.0
    assert out[1]["category"] == "b"


def test_complete_uses_judge_model():
    llm = _warehouse([["a cluster name"]])
    assert llm.complete("name this cluster") == "a cluster name"
    assert "ai_query('strong', txt)" in llm.calls[0][0]


def test_embed_without_embed_fn_explains_the_local_option():
    llm = _warehouse([])
    with pytest.raises(LLMError, match="embed_fn"):
        llm.embed(["a"])


# ---- provider factory ------------------------------------------------------
def _configured(cfg, **overrides):
    """cfg with a platform chosen (config.example.yaml ships none on purpose)."""
    models = replace(cfg.models, sql_template="ai_query('{model}', {input})",
                     classifier="cheap-model", judge="strong-model")
    fields = {"models": models, "sql_url": "databricks://token@host/db"}
    fields.update(overrides)          # caller wins, e.g. sql_url=""
    return replace(cfg, **fields)


def test_client_is_built_without_any_api_key(cfg, monkeypatch):
    """The whole point: Steps 2-5 start with a warehouse URL and no API key."""
    cfg = _configured(cfg)
    created = {}

    def fake_client(**kw):
        created.update(kw)
        return "client"

    monkeypatch.setattr(pipeline, "WarehouseClient", fake_client)
    assert pipeline._make_llm(cfg) == "client"
    assert created["sql_template"] == cfg.models.sql_template
    assert created["url"] == "databricks://token@host/db"
    # models keep the cost-aware split between a cheap pass and a stronger judge
    assert created["classifier_model"] == cfg.models.classifier
    assert created["judge_model"] == cfg.models.judge


def test_shipped_example_config_picks_no_platform(cfg):
    """Neutral by design: the example must not quietly default to one vendor."""
    assert cfg.models.sql_template == ""
    assert cfg.models.classifier == "" and cfg.models.judge == ""


def test_missing_sql_template_explains_both_platforms(cfg):
    cfg = replace(cfg, sql_url="databricks://token@host/db")   # template still empty
    with pytest.raises(RuntimeError) as e:
        pipeline._make_llm(cfg)
    msg = str(e.value)
    assert "ai_query" in msg and "CORTEX.COMPLETE" in msg
    assert "FN(model, prompt)" in msg  # the rule for unlisted platforms
    assert "agent-metrics" in msg      # the credential-free deterministic path


def test_missing_model_names_is_reported_before_querying(cfg):
    cfg = replace(cfg,
                  models=replace(cfg.models, sql_template="ai_query('{model}', {input})"),
                  sql_url="databricks://token@host/db")
    with pytest.raises(RuntimeError) as e:
        pipeline._make_llm(cfg)
    msg = str(e.value)
    assert "classifier" in msg and "judge" in msg


def test_missing_connection_url_names_the_env_var(cfg):
    cfg = _configured(cfg, sql_url="")
    with pytest.raises(RuntimeError) as e:
        pipeline._make_llm(cfg)
    msg = str(e.value)
    assert cfg.models.sql_url_env in msg
    assert "agent-metrics" in msg     # Steps 1 and 6 still need nothing


def test_unknown_provider_points_at_the_interface(cfg):
    cfg = _configured(cfg)
    cfg = replace(cfg, models=replace(cfg.models, provider="banana"))
    with pytest.raises(RuntimeError, match="LLMClient"):
        pipeline._make_llm(cfg)


def test_connection_url_comes_from_the_configured_env_var(tmp_path, monkeypatch):
    """The URL is a secret: it lives in the environment, never in the YAML."""
    from helpers import REPO_ROOT
    from hire_pipeline.config import load_config

    monkeypatch.setenv("MY_WAREHOUSE_URL", "snowflake://acct/db")
    text = (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    text = text.replace("taxonomy_file: taxonomy.yaml",
                        f"taxonomy_file: {REPO_ROOT / 'taxonomy.yaml'}")
    text = text.replace("sql_url_env:  HIRE_SQL_URL", "sql_url_env: MY_WAREHOUSE_URL")
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")

    cfg = load_config(str(p))
    assert cfg.sql_url == "snowflake://acct/db"
    assert "MY_WAREHOUSE_URL" not in text.split("sql_url_env")[0]  # not a literal secret
