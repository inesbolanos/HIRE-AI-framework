"""Steps 3 and 5: auditing the 'other' bucket, and the discovery that consumes it.

Step 3 is what stops 'other' becoming a dumping ground — it re-checks every row
sent there and can overturn the call. Step 5 then clusters only the rows the audit
*confirmed*. Both were previously untested.
"""
import pandas as pd

from hire_pipeline import audit, topic_discovery
from hire_pipeline import constants as const
from hire_pipeline.llm import LLMClient


class AuditLLM(LLMClient):
    """Canned audit verdicts keyed by the text under review."""

    def __init__(self, verdicts):
        self.verdicts = verdicts
        self.models_used = []

    def classify(self, prompt, text_value, schema, model=None):
        self.models_used.append(model)
        return self.verdicts.get(text_value, {
            const.OTHER_CORRECT: True, "corrected_category": None,
            "reason_theme": "misc", const.NEEDS_REVIEW: False})


def _classified(store, cfg, rows):
    store.write(cfg.tables.classified, pd.DataFrame(rows))


def _other_row(iid, text):
    return {"interaction_id": iid, "input_text": text,
            "input_category": const.OTHER, "input_status": const.AUTO}


# ---- Step 3: audit --------------------------------------------------------
def test_only_other_rows_are_audited(store, cfg):
    _classified(store, cfg, [
        _other_row("i1", "is my money safe?"),
        {"interaction_id": "i2", "input_text": "someone used my card",
         "input_category": "report_unauthorized_transaction", "input_status": const.AUTO},
    ])
    assert audit.audit_other(store, cfg, AuditLLM({})) == 1
    assert store.ids(cfg.tables.audit) == {"i1"}


def test_the_audit_can_overturn_other_and_name_the_real_category(store, cfg):
    """The point of Step 3: catching a KNOWN category that Step 2 wrongly discarded."""
    _classified(store, cfg, [_other_row("i1", "someone used my card")])
    llm = AuditLLM({"someone used my card": {
        const.OTHER_CORRECT: False,
        "corrected_category": "report_unauthorized_transaction",
        "reason_theme": "unauthorized charge", const.NEEDS_REVIEW: False}})
    audit.audit_other(store, cfg, llm)

    row = store.read(cfg.tables.audit).iloc[0]
    assert bool(row[f"input_{const.OTHER_CORRECT}"]) is False
    assert row["input_corrected_category"] == "report_unauthorized_transaction"


def test_a_null_like_corrected_category_is_normalised_away(store, cfg):
    """Models spell "no value" as null / "null" / "None" / "" — all of which must
    land as a real None, not a literal string that later compares unequal to None."""
    sentinels = ("null", "None", "", None)
    _classified(store, cfg, [_other_row(f"i{i}", f"text {i}")
                             for i in range(len(sentinels))])
    llm = AuditLLM({f"text {i}": {
        const.OTHER_CORRECT: True, "corrected_category": s,
        "reason_theme": "t", const.NEEDS_REVIEW: False}
        for i, s in enumerate(sentinels)})

    audit.audit_other(store, cfg, llm)
    out = store.read(cfg.tables.audit).set_index("interaction_id")
    for i, sentinel in enumerate(sentinels):
        got = out.loc[f"i{i}", "input_corrected_category"]
        assert got is None or pd.isna(got), f"{sentinel!r} survived as {got!r}"


def test_needs_review_hands_the_row_to_a_human(store, cfg):
    _classified(store, cfg, [_other_row("i1", "garbled ???")])
    llm = AuditLLM({"garbled ???": {
        const.OTHER_CORRECT: True, "corrected_category": None,
        "reason_theme": "unclear", const.NEEDS_REVIEW: True}})
    audit.audit_other(store, cfg, llm)

    q = store.read(cfg.tables.review)
    assert len(q) == 1
    assert q.iloc[0]["input_stage"] == "audit"


def test_the_audit_uses_the_stronger_judge_model(store, cfg):
    _classified(store, cfg, [_other_row("i1", "t")])
    llm = AuditLLM({})
    audit.audit_other(store, cfg, llm)
    assert llm.models_used == [cfg.models.judge]


def test_audit_skips_other_rows_with_no_text(store, cfg):
    _classified(store, cfg, [
        {"interaction_id": "i1", "input_text": "   ", "input_category": const.OTHER},
        {"interaction_id": "i2", "input_text": None, "input_category": const.OTHER},
    ])
    assert audit.audit_other(store, cfg, AuditLLM({})) == 0


def test_audit_is_incremental(store, cfg):
    _classified(store, cfg, [_other_row("i1", "t")])
    llm = AuditLLM({})
    assert audit.audit_other(store, cfg, llm) == 1
    calls = len(llm.models_used)
    assert audit.audit_other(store, cfg, llm) == 0
    assert len(llm.models_used) == calls


def test_no_classified_table_is_a_quiet_no_op(store, cfg):
    assert audit.audit_other(store, cfg, AuditLLM({})) == 0


# ---- Step 5: discovery ----------------------------------------------------
def test_discovery_skips_cleanly_with_no_audited_rows(store, cfg):
    """Step 5 is optional by design: no audit table yet must be a logged skip, not
    a crash, so the rest of the pipeline still completes."""
    assert topic_discovery.discover_topics(store, cfg, AuditLLM({})) == 0


def test_discovery_skips_cleanly_when_the_audit_table_lacks_its_columns(store, cfg):
    store.write(cfg.tables.audit, pd.DataFrame([{"interaction_id": "i1"}]))
    assert topic_discovery.discover_topics(store, cfg, AuditLLM({})) == 0


def test_discovery_eligibility_excludes_overturned_and_pending_rows(store, cfg):
    """Only rows the audit CONFIRMED as 'other' are candidate emergent topics:
    an overturned row belongs to a known category, and a needs_review row is still
    pending a human. Asserted through the public entry point, which returns 0
    because every row is filtered out before any clustering is attempted."""
    store.write(cfg.tables.audit, pd.DataFrame([
        {"interaction_id": "i1", "input_text": "confirmed other",
         f"input_{const.OTHER_CORRECT}": False, f"input_{const.NEEDS_REVIEW}": False},
        {"interaction_id": "i2", "input_text": "pending",
         f"input_{const.OTHER_CORRECT}": True, f"input_{const.NEEDS_REVIEW}": True},
        {"interaction_id": "i3", "input_text": "   ",
         f"input_{const.OTHER_CORRECT}": True, f"input_{const.NEEDS_REVIEW}": False},
    ]))
    assert topic_discovery.discover_topics(store, cfg, AuditLLM({})) == 0
