"""Gold-set scoring + confidence-threshold calibration."""
from pathlib import Path

import pytest

from hire_pipeline import evaluation
from hire_pipeline import constants as const


# ---- a bad gold set is a user situation, not a crash -----------------------
def test_missing_gold_file_is_reported_clearly(tmp_path):
    with pytest.raises(ValueError) as e:
        evaluation.load_gold(str(Path(tmp_path) / "nope.csv"))
    assert "not found" in str(e.value)


def test_gold_set_with_a_mislabeled_header_is_rejected(tmp_path):
    """Without the check this surfaced as a bare KeyError from whichever caller
    first read the column."""
    bad = Path(tmp_path) / "gold.csv"
    bad.write_text("interaction_id,category\ni1,report_phishing\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        evaluation.load_gold(str(bad))
    assert "gold_category" in str(e.value)


def test_confidence_coercion_is_the_shared_helper(tmp_path):
    """evaluation.py used to carry a private `_f` that was byte-identical to
    store.to_float. Calibration must still tolerate str / None confidences."""
    from hire_pipeline.store import to_float
    gold_map = {"i1": "report_phishing", "i2": "report_phishing"}
    rows = [
        {"interaction_id": "i1", "category": "report_phishing", "confidence": "0.95"},
        {"interaction_id": "i2", "category": "report_phishing", "confidence": None},
    ]
    out = evaluation.calibrate_threshold(rows, gold_map, target_precision=0.5)
    assert out["chosen_threshold"] >= 0.0
    assert to_float("0.95") == 0.95 and to_float(None) == 0.0


def test_valid_gold_set_loads(tmp_path):
    good = Path(tmp_path) / "gold.csv"
    good.write_text("interaction_id,gold_category\ni1,report_phishing\n", encoding="utf-8")
    assert evaluation.load_gold(str(good)) == [
        {"interaction_id": "i1", "gold_category": "report_phishing"}]


def test_score_accuracy_and_leak_rates():
    gold = [
        {"interaction_id": "i1", "gold_category": "report_phishing"},
        {"interaction_id": "i2", "gold_category": "report_phishing"},
        {"interaction_id": "i3", "gold_category": const.OTHER},
        {"interaction_id": "i4", "gold_category": "dispute_transaction"},
    ]
    predictions = {
        "i1": "report_phishing",      # correct
        "i2": const.OTHER,            # known leaked into 'other'  -> false_other
        "i3": "report_phishing",      # 'other' leaked into known  -> false_known
        "i4": "dispute_transaction",  # correct
    }
    r = evaluation.score(predictions, gold)
    assert r["n"] == 4
    assert r["accuracy"] == 0.5
    assert r["false_other_rate"] == 1 / 3   # 1 of 3 known-gold rows
    assert r["false_known_rate"] == 1.0     # 1 of 1 other-gold rows
    assert r["per_category"]["dispute_transaction"]["precision"] == 1.0
    assert r["per_category"]["report_phishing"]["recall"] == 0.5


def test_score_only_overlapping_rows_counted():
    gold = [{"interaction_id": "missing", "gold_category": "x"}]
    r = evaluation.score({"i1": "x"}, gold)
    assert r["n"] == 0
    assert r["accuracy"] == 0.0


def test_calibrate_picks_lowest_threshold_meeting_target():
    gold = {"i1": "a", "i2": "a", "i3": "b", "i4": "b"}
    rows = [
        {"interaction_id": "i1", "category": "a", "confidence": 0.95},  # correct
        {"interaction_id": "i2", "category": "b", "confidence": 0.55},  # wrong, low conf
        {"interaction_id": "i3", "category": "b", "confidence": 0.90},  # correct
        {"interaction_id": "i4", "category": "a", "confidence": 0.60},  # wrong, low conf
    ]
    # at threshold 0.50/0.55/0.60 precision < 1.0; from 0.65 both kept rows are correct
    r = evaluation.calibrate_threshold(rows, gold, target_precision=1.0)
    assert r["meets_target"] is True
    assert r["chosen_threshold"] == 0.65


def test_calibrate_unreachable_target_reports_best_effort():
    gold = {"i1": "a"}
    rows = [{"interaction_id": "i1", "category": "b", "confidence": 0.99}]  # always wrong
    r = evaluation.calibrate_threshold(rows, gold, target_precision=0.9)
    assert r["meets_target"] is False
    assert all(s["precision"] == 0.0 for s in r["sweep"] if s["n"])


def test_calibrate_ignores_rows_without_ground_truth():
    gold = {"i1": "a"}
    rows = [
        {"interaction_id": "i1", "category": "a", "confidence": 0.9},
        {"interaction_id": "unlabeled", "category": "zzz", "confidence": 0.9},
    ]
    r = evaluation.calibrate_threshold(rows, gold, target_precision=1.0)
    assert r["meets_target"] is True
    assert r["chosen_threshold"] == 0.5  # the unlabeled row must not drag precision down
