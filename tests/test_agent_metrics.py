"""Step 6: the five headline agent metrics, computed deterministically."""
from dataclasses import replace

import pandas as pd

from hire_pipeline import deterministic_categorization as step1
from hire_pipeline import agent_metrics

from helpers import interaction, seed_source


def _run(store, cfg, rows):
    seed_source(store, cfg, rows)
    step1.apply_rules(store, cfg)
    return agent_metrics.evaluate_metrics(store, cfg)


def _seed_classified(store, cfg, rows):
    """Write a Step 2 table. Its column names come from the role prefixes in
    Config.roles(), so they are fixed regardless of the Step 1 column config."""
    store.write(cfg.tables.classified, pd.DataFrame(rows))


def test_instant_resolution_and_ping_pong(store, cfg):
    rates = _run(store, cfg, [
        # conv A: lost card -> blocked on turn 1 = instant resolution
        interaction("i1", "A", 1, control="qr_lost_card", action="block_card"),
        interaction("i2", "A", 2, control="qr_end"),
        # conv B: dispute filed only on turn 3 = resolved but not instant
        interaction("i3", "B", 1, control="qr_unauth_txn"),
        interaction("i4", "B", 2, control="form_dispute"),
        interaction("i5", "B", 3, action="file_dispute"),
    ])
    assert rates["instant_resolution_rate"] == 0.5      # A yes, B no
    assert rates["ping_pong_rate"] == 2.0               # mean of turns 1 and 3
    assert rates["diy_rate"] == 0.0


def test_red_line_from_pattern_and_diy_when_abandoned(store, cfg):
    rates = _run(store, cfg, [
        # conv A: agent reply leaks a credential-style string -> red line pattern
        interaction("i1", "A", 1, control="qr_ato",
                    agent_output="Your PIN is 4321, please keep it safe."),
        # conv B: clean, resolved
        interaction("i2", "B", 1, control="qr_lost_card", action="block_card"),
        interaction("i3", "B", 2, control="qr_end"),
    ])
    assert abs(rates["red_line_rate"] - 1 / 3) < 1e-9   # 1 of 3 interactions
    # conv A never got its resolving action and never formally closed -> DIY
    assert rates["diy_rate"] == 0.5


def test_no_red_line_on_clean_conversations(store, cfg):
    rates = _run(store, cfg, [
        interaction("i1", "A", 1, control="qr_phishing", action="secure_account",
                    agent_output="I've secured your account and flagged the email."),
        interaction("i2", "A", 2, control="qr_end"),
    ])
    assert rates["red_line_rate"] == 0.0
    assert rates["user_correction_rate"] == 0.0


def test_llm_labels_feed_correction_and_red_line(store, cfg):
    """The LLM-dependent half of the metrics: 'correction' and a red-line output
    category only ever come from Step 2, so UCR and category-based RLR are zero
    without them."""
    seed_source(store, cfg, [
        interaction("i1", "A", 1, user_input="No, that's wrong, I said March 15th.",
                    agent_output="100% you'll get your money back."),
    ])
    step1.apply_rules(store, cfg)
    _seed_classified(store, cfg, [{
        "interaction_id": "i1",
        "input_category": "correction",
        "output_category": "overpromise_guarantee",
        "input_tone": "frustrated",
    }])
    rates = agent_metrics.evaluate_metrics(store, cfg)
    assert rates["user_correction_rate"] == 1.0
    assert rates["red_line_rate"] == 1.0          # via category, not regex


def test_renaming_deterministic_columns_keeps_the_llm_signal(store, cfg):
    """Regression: the Step 2 columns used to be located via merge(suffixes=...),
    which only fires on a NAME COLLISION with the Step 1 columns. Renaming the
    Step 1 columns — which config.yaml explicitly invites — silently dropped the
    LLM signal, so UCR and category red lines read zero on a 'successful' run."""
    cfg = replace(cfg, deterministic=replace(
        cfg.deterministic, input_category="det_user_cat", output_category="det_agent_cat"))

    seed_source(store, cfg, [
        interaction("i1", "A", 1, user_input="No, that's wrong, I said March 15th.",
                    agent_output="100% you'll get your money back."),
    ])
    step1.apply_rules(store, cfg)
    _seed_classified(store, cfg, [{
        "interaction_id": "i1",
        "input_category": "correction",
        "output_category": "overpromise_guarantee",
        "input_tone": "frustrated",
    }])

    df = agent_metrics._enrich(store, cfg)
    assert df["eff_intent"].tolist() == ["correction"]
    assert df["llm_output_cat"].tolist() == ["overpromise_guarantee"]
    assert df["tone"].tolist() == ["frustrated"]

    rates = agent_metrics.evaluate_metrics(store, cfg)
    assert rates["user_correction_rate"] == 1.0
    assert rates["red_line_rate"] == 1.0


def test_zero_indexed_turns_still_score_instant_resolutions(store, cfg):
    """Regression: `instant` was hardcoded as turn == 1, so 0-indexed source data
    silently produced instant_resolution_rate == 0.0 with no error. The first turn
    present is now what counts as the first exchange."""
    rates = _run(store, cfg, [
        interaction("i1", "A", 0, control="qr_lost_card", action="block_card"),
        interaction("i2", "A", 1, control="qr_end"),
    ])
    assert rates["instant_resolution_rate"] == 1.0
    assert rates["ping_pong_rate"] == 0.0        # the turn index itself, unshifted


def test_turn_column_is_renameable(store, cfg):
    """`turn` used to be hardcoded in three places while conversation_id came from
    config — so renaming it raised KeyError deep inside Step 6."""
    from dataclasses import replace as dc_replace
    cfg = dc_replace(cfg, columns=dc_replace(cfg.columns, turn="exchange_no"))

    rows = [interaction("i1", "A", 1, control="qr_lost_card", action="block_card")]
    for r in rows:
        r["exchange_no"] = r.pop("turn")
    seed_source(store, cfg, rows)
    step1.apply_rules(store, cfg)

    rates = agent_metrics.evaluate_metrics(store, cfg)
    assert rates["instant_resolution_rate"] == 1.0
    assert store.read(cfg.tables.conversation_metrics).iloc[0]["turns"] == 1


def test_conversation_flags_table_written(store, cfg):
    _run(store, cfg, [
        interaction("i1", "A", 1, control="qr_lost_card", action="block_card"),
    ])
    conv = store.read(cfg.tables.conversation_metrics)
    assert len(conv) == 1
    row = conv.iloc[0]
    assert row["conversation_id"] == "A"
    assert bool(row["resolved"]) is True
    assert bool(row["instant_resolution"]) is True
