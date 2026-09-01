"""Step 4: HITL (human-in-the-loop) queue.

Whatever the automated layers can't confidently resolve lands here for a human:

  * from Step 2 escalation — rows still below the confidence threshold after the
    stronger model re-checked them;
  * from Step 3 audit — 'other' rows the stronger model flagged as unsure
    ('needs_review') rather than confirming 'other' or correcting the category.

The queue is wide: one row per interaction, with the user-side flag in 'input_*'
columns and the agent-side flag in 'output_*' columns.

The human's decisions are the ground-truth feedback that improves the prompts /
few-shots and the deterministic router, i.e. the flywheel. This module owns the
queue's shape and the merge; the producers (escalation, audit) call it.
"""
from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from .config import Config
from .store import Store, run_ts


def make_row(interaction_id: str, role: str, stage: str, text: str,
             category: Optional[str], confidence, reason: str) -> dict:
    """Build one role-specific queue partial. 'role' is 'input' or 'output';
    'stage' records which step flagged it ('escalation' or 'audit'); 'category'
    is the best current guess (may be 'other' or None). Merged into the interaction's
    row by 'enqueue'."""
    return {
        "interaction_id": interaction_id,
        f"{role}_stage": stage,
        f"{role}_text": text,
        f"{role}_category": category,
        f"{role}_confidence": confidence,
        f"{role}_reason": reason,
        "run_ts": run_ts(),
    }


def enqueue(store: Store, cfg: Config, rows: Sequence[dict]) -> int:
    """Merge role partials into the HITL queue, one row per interaction. Returns the
    number of partials merged.

    A partial only carries its own role's columns, so merging by interaction_id lets
    an interaction accumulate both an input flag and an output flag without a 'side'
    row. Re-runs overwrite the same columns, so this stays dupe-free.
    """
    rows = list(rows)
    if not rows:
        return 0

    df = store.read(cfg.tables.review)
    merged = {r["interaction_id"]: dict(r) for r in df.to_dict("records")} if not df.empty else {}
    for partial in rows:
        iid = partial["interaction_id"]
        row = merged.get(iid, {"interaction_id": iid})
        row.update(partial)
        merged[iid] = row

    store.write(cfg.tables.review, pd.DataFrame(list(merged.values())))
    return len(rows)
