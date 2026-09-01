"""Step 1: deterministic rules, coverage, resolution, and the LLM residual."""
import pandas as pd
import pytest

from hire_pipeline import deterministic_categorization as step1
from hire_pipeline import constants as const

from helpers import interaction, seed_source


def _seed_and_apply(store, cfg, rows):
    seed_source(store, cfg, rows)
    step1.apply_rules(store, cfg)
    return store.read(cfg.tables.deterministic)


def test_source_without_routing_signals_is_reported_not_a_keyerror(store, cfg):
    """A source table lacking the signal columns used to raise a bare KeyError from
    inside apply_rules, which the CLI's handler doesn't catch — so the user got a
    traceback instead of the schema guidance."""
    store.write(cfg.tables.source, pd.DataFrame([
        {"interaction_id": "i1", "conversation_id": "c1", "turn": 1,
         "event_date": "2024-01-01", "user_input": "hi", "agent_output": "hello"},
    ]))
    with pytest.raises(ValueError) as e:
        step1.apply_rules(store, cfg)
    msg = str(e.value)
    assert "user_control_id" in msg and "agent_action_id" in msg


def test_routing_signal_columns_are_renameable(cfg, store):
    """These two used to be module constants, so they were the only source columns
    that couldn't be renamed — and they're the likeliest to differ in real
    telemetry (button_id, tool_call_id, ...)."""
    from dataclasses import replace as dc_replace
    cfg = dc_replace(cfg, columns=dc_replace(
        cfg.columns, user_signal="widget_id", agent_signal="tool_call_id"))

    row = interaction("i1", "c1", 1, control="qr_phishing", action="secure_account")
    row["widget_id"] = row.pop("user_control_id")
    row["tool_call_id"] = row.pop("agent_action_id")
    seed_source(store, cfg, [row])

    step1.apply_rules(store, cfg)
    det = store.read(cfg.tables.deterministic).iloc[0]
    assert det[cfg.deterministic.input_category] == "report_phishing"
    assert det[cfg.deterministic.output_category] == "account_secured"


def test_required_source_columns_covers_what_the_steps_read(cfg):
    required = step1.required_source_columns(cfg)
    for col in (cfg.columns.interaction_id, cfg.columns.conversation_id, "turn",
                cfg.columns.date, cfg.columns.input_text, cfg.columns.output_text,
                "user_control_id", "agent_action_id"):
        assert col in required, col


def test_apply_rules_maps_controls_and_actions(store, cfg):
    det = _seed_and_apply(store, cfg, [
        interaction("i1", "c1", 1, control="qr_phishing", action="secure_account"),
        interaction("i2", "c1", 2, user_input="free text q", agent_output="free text a"),
    ])
    r = det.set_index("interaction_id")
    assert r.loc["i1", cfg.deterministic.input_category] == "report_phishing"
    assert r.loc["i1", cfg.deterministic.output_category] == "account_secured"
    # nothing matched -> the freeform labels (Step 2's input)
    assert r.loc["i2", cfg.deterministic.input_category] == cfg.deterministic.freeform_input_label
    assert r.loc["i2", cfg.deterministic.output_category] == cfg.deterministic.freeform_output_label


def test_apply_rules_is_idempotent_and_source_untouched(store, cfg):
    rows = [interaction("i1", "c1", 1, control="qr_end")]
    _seed_and_apply(store, cfg, rows)
    step1.apply_rules(store, cfg)  # re-run must not duplicate or drift
    det = store.read(cfg.tables.deterministic)
    assert len(det) == 1
    src = store.read(cfg.tables.source)
    assert cfg.deterministic.input_category not in src.columns


def test_resolve_conversation_all_four_statuses(cfg):
    resolving = cfg.taxonomy.intent_resolving_actions
    # agent took a resolving action for the stated intent
    assert step1.resolve_conversation(
        {"report_lost_stolen_card"}, {"card_blocked"}, False, resolving) == const.RESOLVED
    # expected an action, none came, user formally closed
    assert step1.resolve_conversation(
        {"report_lost_stolen_card"}, set(), True, resolving) == const.UNRESOLVED
    # expected an action, none came, user just left
    assert step1.resolve_conversation(
        {"report_lost_stolen_card"}, set(), False, resolving) == const.ABANDONED
    # no intent with a known resolving action -> can't judge
    assert step1.resolve_conversation(
        {"end_conversation"}, set(), True, resolving) == const.UNDETERMINED
    assert step1.resolve_conversation(set(), set(), False, resolving) == const.UNDETERMINED


def test_derive_resolution_counts(store, cfg):
    _seed_and_apply(store, cfg, [
        # c1 resolved: lost card -> card blocked
        interaction("i1", "c1", 1, control="qr_lost_card", action="block_card"),
        # c2 unresolved: intent stated, no action, formally closed
        interaction("i2", "c2", 1, control="qr_unauth_txn"),
        interaction("i3", "c2", 2, control="qr_end"),
        # c3 abandoned: intent stated, no action, no close
        interaction("i4", "c3", 1, control="qr_ato"),
    ])
    counts = step1.derive_resolution(store, cfg)
    assert counts[const.RESOLVED] == 1
    assert counts[const.UNRESOLVED] == 1
    assert counts[const.ABANDONED] == 1
    assert counts[const.UNDETERMINED] == 0


def test_compute_coverage(store, cfg):
    _seed_and_apply(store, cfg, [
        interaction("i1", "c1", 1, control="qr_phishing"),
        interaction("i2", "c1", 2, control="qr_end"),
        interaction("i3", "c1", 3, user_input="free text"),
    ])
    cov = step1.compute_coverage(store, cfg)
    assert cov["input"]["total"] == 3
    assert cov["input"]["covered"] == 2
    assert abs(cov["input"]["coverage"] - 2 / 3) < 1e-9
    assert cov["output"]["covered"] == 0  # no agent actions above


def test_coverage_trend_is_per_day_and_sorted(store, cfg):
    _seed_and_apply(store, cfg, [
        interaction("i1", "c1", 1, date="2024-01-02", control="qr_phishing"),
        interaction("i2", "c2", 1, date="2024-01-01", control="qr_end"),
        interaction("i3", "c2", 2, date="2024-01-01", user_input="free text"),
    ])
    trend = step1.coverage_trend(store, cfg, "input")
    assert [t["date_value"] for t in trend] == ["2024-01-01", "2024-01-02"]
    assert trend[0]["deterministic_coverage"] == 0.5
    assert trend[1]["deterministic_coverage"] == 1.0


def test_freeform_residual_skips_empty_text(store, cfg):
    _seed_and_apply(store, cfg, [
        interaction("i1", "c1", 1, user_input="help with a strange charge"),
        interaction("i2", "c1", 2, user_input="   "),          # blank -> not classifiable
        interaction("i3", "c1", 3, control="qr_phishing"),      # routed -> not residual
    ])
    role = next(r for r in cfg.roles() if r["prefix"] == "input")
    residual = step1.freeform_residual(store, cfg, role)
    assert [r["interaction_id"] for r in residual] == ["i1"]
    assert residual[0]["text_value"] == "help with a strange charge"
