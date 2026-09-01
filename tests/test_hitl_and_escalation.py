"""Steps 2-4: escalation to the judge, and the HITL queue it feeds.

These are the pipeline's cost-control and human-feedback mechanisms — the reason
most rows stay on the cheap model and only genuinely ambiguous ones get paid for
twice. Both were previously untested.
"""
import pandas as pd
import pytest

from hire_pipeline import constants as const
from hire_pipeline import escalation, hitl_queue
from hire_pipeline.llm import LLMClient


class JudgeLLM(LLMClient):
    """Canned judge answers keyed by the text under review."""

    def __init__(self, answers):
        self.answers = answers
        self.models_used = []

    def classify(self, prompt, text_value, schema, model=None):
        self.models_used.append(model)
        category, confidence = self.answers.get(text_value, (const.OTHER, 0.9))
        return {"category": category, "confidence": confidence, "reason": "judged",
                "tone": "neutral"}


def _classified(store, cfg, rows):
    store.write(cfg.tables.classified, pd.DataFrame(rows))


# ---- hitl_queue: the wide merge is this module's whole claim ----------------
def test_two_roles_of_one_interaction_merge_into_a_single_row(store, cfg):
    """The central design claim: an interaction can accumulate an input flag AND
    an output flag across two separate enqueue calls without duplicating rows."""
    hitl_queue.enqueue(store, cfg, [
        hitl_queue.make_row("i1", "input", "escalation", "user text", "other", 0.4, "unsure"),
    ])
    hitl_queue.enqueue(store, cfg, [
        hitl_queue.make_row("i1", "output", "audit", "agent text", None, None, "theme"),
    ])
    q = store.read(cfg.tables.review)
    assert len(q) == 1, "the second enqueue must merge, not append a second row"
    row = q.iloc[0]
    assert row["input_stage"] == "escalation"
    assert row["output_stage"] == "audit"
    assert row["input_text"] == "user text"
    assert row["output_text"] == "agent text"


def test_re_enqueueing_the_same_role_overwrites_rather_than_duplicates(store, cfg):
    hitl_queue.enqueue(store, cfg, [
        hitl_queue.make_row("i1", "input", "escalation", "first", "other", 0.4, "a")])
    hitl_queue.enqueue(store, cfg, [
        hitl_queue.make_row("i1", "input", "escalation", "second", "other", 0.5, "b")])
    q = store.read(cfg.tables.review)
    assert len(q) == 1
    assert q.iloc[0]["input_text"] == "second"


def test_enqueue_of_nothing_is_a_no_op(store, cfg):
    assert hitl_queue.enqueue(store, cfg, []) == 0
    assert store.read(cfg.tables.review).empty


def test_distinct_interactions_get_distinct_rows(store, cfg):
    hitl_queue.enqueue(store, cfg, [
        hitl_queue.make_row("i1", "input", "audit", "a", "other", 0.4, ""),
        hitl_queue.make_row("i2", "input", "audit", "b", "other", 0.4, ""),
    ])
    assert store.ids(cfg.tables.review) == {"i1", "i2"}


# ---- escalation: only ESCALATE rows, judged, then AUTO or HITL --------------
def test_only_escalate_rows_reach_the_judge(store, cfg):
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "confident one",
         "input_category": "report_phishing", "input_status": const.AUTO},
        {"interaction_id": "i2", "input_text": "ambiguous one",
         "input_category": const.OTHER, "input_status": const.ESCALATE},
    ])
    llm = JudgeLLM({"ambiguous one": ("report_phishing", 0.95)})
    assert escalation.escalate_low_confidence(store, cfg, llm) == 1

    esc = store.read(cfg.tables.escalation).set_index("interaction_id")
    assert list(esc.index) == ["i2"], "the AUTO row must not be re-judged"
    assert esc.loc["i2", "input_category"] == "report_phishing"
    assert esc.loc["i2", "input_prev_category"] == const.OTHER


def test_the_judge_model_is_used_not_the_classifier(store, cfg):
    """Escalation exists to buy a second opinion from a *stronger* model; sending
    it back to the cheap one would make the whole step pointless."""
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "t", "input_category": const.OTHER,
         "input_status": const.ESCALATE}])
    llm = JudgeLLM({})
    escalation.escalate_low_confidence(store, cfg, llm)
    assert llm.models_used == [cfg.models.judge]


def test_still_unsure_after_the_judge_goes_to_the_human_queue(store, cfg):
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "hopeless", "input_category": const.OTHER,
         "input_status": const.ESCALATE}])
    llm = JudgeLLM({"hopeless": (const.OTHER, 0.1)})       # below threshold again
    escalation.escalate_low_confidence(store, cfg, llm)

    q = store.read(cfg.tables.review)
    assert len(q) == 1
    assert q.iloc[0]["interaction_id"] == "i1"
    assert q.iloc[0]["input_stage"] == "escalation"


def test_confident_after_the_judge_stays_out_of_the_queue(store, cfg):
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "resolvable", "input_category": const.OTHER,
         "input_status": const.ESCALATE}])
    llm = JudgeLLM({"resolvable": ("report_phishing", 0.99)})
    escalation.escalate_low_confidence(store, cfg, llm)
    assert store.read(cfg.tables.review).empty


def test_escalation_is_incremental(store, cfg):
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "t", "input_category": const.OTHER,
         "input_status": const.ESCALATE}])
    llm = JudgeLLM({})
    assert escalation.escalate_low_confidence(store, cfg, llm) == 1
    calls = len(llm.models_used)
    assert escalation.escalate_low_confidence(store, cfg, llm) == 0
    assert len(llm.models_used) == calls, "an already-escalated row must not be re-judged"


def test_no_classified_table_is_a_quiet_no_op(store, cfg):
    assert escalation.escalate_low_confidence(store, cfg, JudgeLLM({})) == 0


def test_a_classified_table_without_status_columns_is_survivable(store, cfg):
    """Guard the `if status_col not in columns: continue` branch — a partially
    written Step 2 table must not crash the step."""
    _classified(store, cfg, [{"interaction_id": "i1", "input_text": "t"}])
    assert escalation.escalate_low_confidence(store, cfg, JudgeLLM({})) == 0
