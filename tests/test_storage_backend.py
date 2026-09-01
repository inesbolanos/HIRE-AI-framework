"""Storage wiring: the pipeline's tables always live in a database.

Covers where the connection URL comes from (never the YAML), the SQLite fallback
that keeps the sample data runnable with no server or credentials, and the
identifier quoting that the shipped digit-leading table names require.
"""
from dataclasses import replace

import pytest

from hire_pipeline import pipeline
from hire_pipeline.config import Storage
from hire_pipeline.store import SQLStore


# ---- connection selection --------------------------------------------------
def test_defaults_to_a_local_sqlite_database(cfg):
    """No credentials configured must still give a real, working database."""
    assert cfg.store_url.startswith("sqlite:///")
    store = pipeline._make_store(cfg)
    assert isinstance(store, SQLStore)
    assert store.engine.dialect.name == "sqlite"


def test_env_var_overrides_the_default(tmp_path, monkeypatch):
    from helpers import make_cfg
    monkeypatch.setenv("HIRE_STORE_URL", "postgresql+psycopg://u:p@host/db")
    cfg = make_cfg(tmp_path)
    assert cfg.store_url == "postgresql+psycopg://u:p@host/db"


def test_url_env_name_is_configurable(tmp_path, monkeypatch):
    from helpers import REPO_ROOT
    from hire_pipeline.config import load_config

    monkeypatch.setenv("MY_WAREHOUSE", "snowflake://acct/db")
    text = (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    text = text.replace("taxonomy_file: taxonomy.yaml",
                        f"taxonomy_file: {REPO_ROOT / 'taxonomy.yaml'}")
    text = text.replace("url_env:     HIRE_STORE_URL", "url_env: MY_WAREHOUSE")
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    assert load_config(str(p)).store_url == "snowflake://acct/db"


def test_cli_override_wins_over_config(cfg, tmp_path):
    url = f"sqlite:///{tmp_path / 'explicit.db'}"
    store = pipeline._make_store(cfg, url)
    assert isinstance(store, SQLStore)


def test_schema_is_passed_through(cfg, monkeypatch):
    cfg = replace(cfg, storage=Storage(schema="analytics"),
                  store_url="databricks://token@host/db")
    built = {}

    def fake_store(url, schema=None):
        built["url"], built["schema"] = url, schema
        return "sql-store"

    monkeypatch.setattr(pipeline, "SQLStore", fake_store)
    assert pipeline._make_store(cfg) == "sql-store"
    assert built["url"] == "databricks://token@host/db"
    assert built["schema"] == "analytics"


def test_missing_url_explains_both_ways_out(cfg):
    cfg = replace(cfg, storage=Storage(default_url=""), store_url="")
    with pytest.raises(RuntimeError) as e:
        pipeline._make_store(cfg)
    msg = str(e.value)
    assert cfg.storage.url_env in msg
    assert "sqlite" in msg                    # the zero-setup way out


def test_uninstalled_dialect_names_the_package_to_install(cfg):
    """The most likely real-world failure: installing a platform's DBAPI driver
    (databricks-sql-connector) instead of its SQLAlchemy dialect. The raw error
    is 'Can't load plugin', which tells a non-developer nothing."""
    with pytest.raises(RuntimeError) as e:
        pipeline._make_store(cfg, "nosuchplatform://token@host/db")
    msg = str(e.value)
    assert "databricks-sqlalchemy" in msg
    assert "dialect" in msg.lower()


def test_unparseable_url_shows_a_valid_example(cfg):
    with pytest.raises(RuntimeError) as e:
        pipeline._make_store(cfg, "this is not a url")
    assert "sqlite:///hire.db" in str(e.value)


# ---- ingest validates the source schema at the boundary --------------------
def test_missing_source_file_points_at_the_generator(store, cfg, tmp_path):
    with pytest.raises(ValueError) as e:
        pipeline.load_source(store, cfg, str(tmp_path / "nope.csv"))
    assert "generate_sample_data.py" in str(e.value)


def test_source_csv_missing_columns_names_all_of_them(store, cfg, tmp_path):
    """One message listing everything missing, rather than a KeyError from
    whichever step happens to touch a column first."""
    import pandas as pd
    csv_path = tmp_path / "src.csv"
    pd.DataFrame([{"interaction_id": "i1", "conversation_id": "c1"}]).to_csv(
        csv_path, index=False)
    with pytest.raises(ValueError) as e:
        pipeline.load_source(store, cfg, str(csv_path))
    msg = str(e.value)
    for col in ("turn", "user_input", "agent_output", "user_control_id", "agent_action_id"):
        assert col in msg, col


# ---- SQLStore identifier quoting ------------------------------------------
class _FakePreparer:
    def quote(self, identifier):
        return f'"{identifier}"'


class _FakeDialect:
    name = "fakesql"
    identifier_preparer = _FakePreparer()


class _FakeEngine:
    dialect = _FakeDialect()


def _sql_store(schema=None):
    return SQLStore(url="", schema=schema, engine=_FakeEngine())


def test_table_names_starting_with_digits_are_quoted():
    """A renamed table may start with a digit, which is invalid SQL unquoted."""
    store = _sql_store()
    assert store._q("00_raw_agent_interactions") == '"00_raw_agent_interactions"'


def test_schema_qualified_names_quote_both_parts():
    store = _sql_store(schema="analytics")
    assert store._q("01_deterministic_labels") == '"analytics"."01_deterministic_labels"'


def test_column_identifiers_are_quoted_too():
    assert _sql_store()._qi("interaction_id") == '"interaction_id"'


def test_empty_schema_is_treated_as_none():
    """config.yaml ships schema: "" — that must mean 'default schema', not a schema named ''."""
    store = _sql_store(schema="")
    assert store.schema is None
    assert store._q("06_metrics") == '"06_metrics"'
