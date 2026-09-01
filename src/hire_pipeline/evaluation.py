"""Evaluation & ground truth: the cross-cutting, highest-priority layer.

The LLM layers are only as trustworthy as our measurement of them. This module
scores the pipeline against a human-labeled Gold set and calibrates the confidence
threshold, so "coverage went up" can be attributed to better routing vs. a
drifting classifier.

Gold set format (CSV): columns 'interaction_id', 'text', 'gold_category'
(and optionally 'gold_tone'). A few hundred rows, stratified across known
categories and 'other'.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from . import constants as const
from .store import to_float

_GOLD_COLUMNS = ("interaction_id", "gold_category")


def load_gold(path: str) -> List[Dict[str, str]]:
    """Read the labeled gold set, validating its header.

    Without the check a mislabeled header surfaces later as a bare KeyError from
    whichever caller first reads the column.
    """
    if not os.path.isfile(path):
        raise ValueError(
            f"Gold set not found: {path}\n"
            "Pass --gold with the path to your labeled CSV, or generate the bundled "
            "one:\n  python datasets/fraud-agent/generate_sample_data.py"
        )
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if rows:
        missing = [c for c in _GOLD_COLUMNS if c not in rows[0]]
        if missing:
            raise ValueError(
                f"{os.path.basename(path)} is missing required column(s): {missing}\n"
                f"Found: {sorted(rows[0])}\n"
                "A gold set needs one row per labeled interaction, with the "
                "interaction_id and the human-assigned gold_category."
            )
    return rows


def score(predictions: Dict[str, str], gold: Sequence[Dict[str, str]]) -> Dict:
    """Compute precision/recall per category + false-other / false-known rates.

    'predictions': interaction_id -> predicted category.
    'gold': rows with 'interaction_id' and 'gold_category'.
    Only rows present in both are scored.
    """
    pairs: List[Tuple[str, str]] = []  # (gold, pred)
    for g in gold:
        tid = g["interaction_id"]
        if tid in predictions:
            pairs.append((g["gold_category"], predictions[tid]))

    if not pairs:
        return {"n": 0, "accuracy": 0.0, "per_category": {},
                "false_other_rate": 0.0, "false_known_rate": 0.0, "confusion": {}}

    labels = sorted({g for g, _ in pairs} | {p for _, p in pairs})
    tp = defaultdict(int); fp = defaultdict(int); fn = defaultdict(int)
    confusion: Dict[str, Dict[str, int]] = {g: defaultdict(int) for g in labels}
    correct = 0
    for gold_c, pred_c in pairs:
        confusion[gold_c][pred_c] += 1
        if gold_c == pred_c:
            tp[gold_c] += 1
            correct += 1
        else:
            fp[pred_c] += 1
            fn[gold_c] += 1

    per_category = {}
    for c in labels:
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_category[c] = {"precision": prec, "recall": rec, "f1": f1,
                           "support": tp[c] + fn[c]}

    # false-other: known leaking into 'other' (gold != other, pred == other)
    known_total = sum(1 for g, _ in pairs if g != const.OTHER)
    false_other = sum(1 for g, p in pairs if g != const.OTHER and p == const.OTHER)
    # false-known: 'other' leaking into a category (gold == other, pred != other)
    other_total = sum(1 for g, _ in pairs if g == const.OTHER)
    false_known = sum(1 for g, p in pairs if g == const.OTHER and p != const.OTHER)

    return {
        "n": len(pairs),
        "accuracy": correct / len(pairs),
        "per_category": per_category,
        "false_other_rate": (false_other / known_total) if known_total else 0.0,
        "false_known_rate": (false_known / other_total) if other_total else 0.0,
        "confusion": {g: dict(row) for g, row in confusion.items()},
    }


def calibrate_threshold(
    scored_rows: Sequence[Dict],
    gold: Dict[str, str],
    target_precision: float = 0.9,
    grid: Optional[Sequence[float]] = None,
) -> Dict:
    """Sweep the confidence cutoff on the gold set; pick the lowest threshold that
    meets target precision on the known (non-'other') predictions.

    'scored_rows': iterable of {interaction_id, category, confidence}. Only rows
    present in 'gold' are scored: the rest have no ground truth to judge against.
    'gold': interaction_id -> gold_category.
    Returns the chosen threshold plus the full sweep so you can inspect the curve.
    Also a reminder to confirm confidence actually correlates with correctness.
    """
    grid = grid or [i / 100 for i in range(50, 100, 5)]  # 0.50 .. 0.95
    # Precision can only be judged on rows we have ground truth for; rows absent
    # from the gold set would otherwise count as wrong and understate precision.
    labeled = [r for r in scored_rows if r.get("interaction_id") in gold]
    sweep = []
    for thr in grid:
        kept = [r for r in labeled
                if to_float(r.get("confidence")) >= thr and r.get("category") != const.OTHER]
        if not kept:
            sweep.append({"threshold": thr, "precision": 0.0, "coverage": 0.0, "n": 0})
            continue
        correct = sum(1 for r in kept if gold.get(r["interaction_id"]) == r["category"])
        precision = correct / len(kept)
        coverage = len(kept) / len(labeled) if labeled else 0.0
        sweep.append({"threshold": thr, "precision": precision,
                      "coverage": coverage, "n": len(kept)})

    meeting = [s for s in sweep if s["precision"] >= target_precision]
    chosen = min(meeting, key=lambda s: s["threshold"]) if meeting else max(
        sweep, key=lambda s: s["precision"])
    return {"chosen_threshold": chosen["threshold"], "target_precision": target_precision,
            "meets_target": bool(meeting), "sweep": sweep}
