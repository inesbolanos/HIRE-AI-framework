"""The shipped taxonomy.yaml + config.example.yaml are internally consistent, and
a broken edit is rejected rather than silently ignored.

These are the invariants the pipeline code relies on (config._validate_taxonomy
enforces some; the rest are checked here so a taxonomy edit fails fast in CI).
"""
from pathlib import Path

import pytest
import yaml

from hire_pipeline import constants as const
from hire_pipeline.config import load_config

from helpers import REPO_ROOT


def _write_taxonomy(tmp_path, mutate):
    """Copy the shipped taxonomy, apply `mutate`, and load a Config pointed at it."""
    tax = yaml.safe_load((REPO_ROOT / "taxonomy.yaml").read_text(encoding="utf-8"))
    mutate(tax)
    tax_path = Path(tmp_path) / "taxonomy.yaml"
    tax_path.write_text(yaml.safe_dump(tax), encoding="utf-8")

    text = (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    text = text.replace("taxonomy_file: taxonomy.yaml", f"taxonomy_file: {tax_path}")
    cfg_path = Path(tmp_path) / "config.yaml"
    cfg_path.write_text(text, encoding="utf-8")
    return load_config(str(cfg_path))


def test_other_present_in_every_label_set(cfg):
    t = cfg.taxonomy
    assert const.OTHER in t.input_labels
    assert const.OTHER in t.output_labels
    assert const.OTHER in t.tone_labels


def test_end_conversation_wired_to_a_control(cfg):
    t = cfg.taxonomy
    assert const.END_CONVERSATION in t.input_labels
    assert const.END_CONVERSATION in set(t.user_controls.values())


def test_fewshot_examples_use_valid_categories(cfg):
    t = cfg.taxonomy
    for ex in t.input_examples:
        assert ex["category"] in t.input_labels, ex["text"]
    for ex in t.output_examples:
        assert ex["category"] in t.output_labels, ex["text"]


def test_resolving_actions_reference_known_intents_and_actions(cfg):
    t = cfg.taxonomy
    known_actions = set(t.agent_actions.values())
    for intent, actions in t.intent_resolving_actions.items():
        assert intent in t.input_labels, intent
        assert set(actions) <= known_actions, intent


def test_metric_config_references_valid_labels(cfg):
    t = cfg.taxonomy
    assert set(t.red_line_categories) <= set(t.output_labels)
    assert set(t.correction_categories) <= set(t.input_labels)
    assert set(t.escalation_categories) <= set(t.input_labels)
    assert set(t.frustration_tones) <= set(t.tone_labels)


def test_confidence_threshold_in_range(cfg):
    assert 0.0 < cfg.run.confidence_threshold < 1.0


# ---- a broken edit must fail loudly, not silently disable a metric ----------
def test_unknown_key_under_metrics_is_rejected(tmp_path):
    """The bug this prevents: a typo'd metrics key used to be dropped in silence,
    so the metric it configured just read zero on a run that reported success."""
    def mutate(tax):
        tax["metrics"]["clarification_input_categories"] = ["confirm_acknowledge"]

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert "clarification_input_categories" in str(e.value)
    assert "metrics" in str(e.value)


def test_unknown_key_under_rules_is_rejected(tmp_path):
    """Dropping 'intent_resolving_actions' (e.g. by misspelling it) would zero out
    both IRR and PPR at once, so it must not be ignorable."""
    def mutate(tax):
        tax["rules"]["intent_resolving_action"] = tax["rules"].pop("intent_resolving_actions")

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert "intent_resolving_action" in str(e.value)


def test_unknown_top_level_taxonomy_key_is_rejected(tmp_path):
    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, lambda tax: tax.update({"metricz": {}}))
    assert "metricz" in str(e.value)


def test_unknown_top_level_config_key_is_rejected(tmp_path):
    """'storgae:' would otherwise leave you on local SQLite while you believe you
    are pointed at a warehouse."""
    raw = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    raw["storgae"] = raw.pop("storage")
    raw["taxonomy_file"] = str(REPO_ROOT / "taxonomy.yaml")
    cfg_path = Path(tmp_path) / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError) as e:
        load_config(str(cfg_path))
    assert "storgae" in str(e.value)


def test_unknown_intent_in_resolving_actions_is_rejected(tmp_path):
    def mutate(tax):
        tax["rules"]["intent_resolving_actions"]["not_a_real_intent"] = ["card_blocked"]

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert "not_a_real_intent" in str(e.value)


def test_unknown_action_in_resolving_actions_is_rejected(tmp_path):
    def mutate(tax):
        tax["rules"]["intent_resolving_actions"]["dispute_transaction"] = ["not_an_action"]

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert "not_an_action" in str(e.value)


def test_missing_other_label_is_rejected(tmp_path):
    def mutate(tax):
        tax["input_labels"].pop(const.OTHER)

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert const.OTHER in str(e.value)


def test_metric_config_referencing_an_unknown_label_is_rejected(tmp_path):
    def mutate(tax):
        tax["metrics"]["red_line_categories"] = ["no_such_output_label"]

    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, mutate)
    assert "no_such_output_label" in str(e.value)


def test_the_shipped_taxonomy_still_loads(tmp_path):
    """Guard against the checks above being too strict for the real file."""
    cfg = _write_taxonomy(tmp_path, lambda tax: None)
    assert cfg.taxonomy.correction_categories == ["correction"]


# ---- a missing or malformed file is a user situation, not a crash -----------
def test_missing_config_file_points_at_the_example(tmp_path):
    with pytest.raises(ValueError) as e:
        load_config(str(Path(tmp_path) / "nope.yaml"))
    assert "config.example.yaml" in str(e.value)


def test_malformed_yaml_is_reported_as_such(tmp_path):
    bad = Path(tmp_path) / "config.yaml"
    bad.write_text("tables: [oops\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_config(str(bad))
    assert "not valid YAML" in str(e.value)


def test_missing_required_config_block_names_it(tmp_path):
    raw = yaml.safe_load((REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    raw.pop("run")
    raw["taxonomy_file"] = str(REPO_ROOT / "taxonomy.yaml")
    cfg_path = Path(tmp_path) / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_config(str(cfg_path))
    assert "run" in str(e.value)


def test_missing_taxonomy_section_is_reported(tmp_path):
    with pytest.raises(ValueError) as e:
        _write_taxonomy(tmp_path, lambda tax: tax.pop("tone_labels"))
    assert "tone_labels" in str(e.value)
