"""Step 3: audit the 'other' bucket.  "We double-check what we discarded."

A stronger model re-checks every row Step 2 sent to 'other': it judges whether
'other' was correct (catching known categories wrongly discarded) and writes a
freeform 'reason_theme' per row (no predefined list; themes emerge from data).
Rows it still can't confidently resolve are flagged 'needs_review' and handed to
the Step 4 HITL queue.

The confirmed 'other' rows this step produces are the input to Step 5 discovery
(clustering), which consolidates them into named, emergent topics.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from .config import Config
from .store import Store, run_ts
from .llm import LLMClient
from .llm_classify import classify_roles
from . import hitl_queue, prompts, constants as const

logger = logging.getLogger("hire.step3")


def audit_other(store: Store, cfg: Config, llm: LLMClient) -> int:
    """Stronger model re-checks every 'other' classification (user and agent),
    assigns a freeform theme, and flags rows it can't confidently resolve
    ('needs_review') for the HITL queue. Results land in the audit table
    columns, one row per interaction. Returns the number of interactions audited.
    """
    roles = cfg.roles()
    classified = store.read(cfg.tables.classified)
    if classified.empty:
        return 0
    already = store.ids(cfg.tables.audit, "interaction_id")

    # per role, the 'other' rows to re-check: {prefix: {interaction_id: text}}
    texts: Dict[str, Dict[str, str]] = {}
    for role in roles:
        p = role["prefix"]
        cat_col, text_col = f"{p}_category", f"{p}_text"
        if cat_col not in classified.columns:
            continue
        mask = ((classified[cat_col] == const.OTHER)
                & classified[text_col].notna()
                & (classified[text_col].astype(str).str.strip() != ""))
        texts[p] = {r["interaction_id"]: r[text_col]
                    for _, r in classified[mask].iterrows()
                    if r["interaction_id"] not in already}
    todo = sorted({iid for m in texts.values() for iid in m})
    logger.info("[step3] %d interactions with 'other' roles to audit", len(todo))
    if not todo:
        return 0

    prompt = {r["prefix"]: prompts.build_other_audit_prompt(cfg, r["taxonomy_role"], cfg.run.language_hint)
              for r in roles}
    audit_schema = {"type": "object",
                    "properties": {const.OTHER_CORRECT: {"type": "boolean"},
                                   "corrected_category": {"type": "string"},
                                   "reason_theme": {"type": "string"},
                                   const.NEEDS_REVIEW: {"type": "boolean"}},
                    "required": [const.OTHER_CORRECT, "reason_theme"]}
    schema = {r["prefix"]: audit_schema for r in roles}

    written = 0
    miscategorized = 0
    queued = 0
    for start in range(0, len(todo), cfg.run.batch_size):
        batch = todo[start:start + cfg.run.batch_size]
        results = classify_roles(llm, cfg.models.judge, batch, texts,
                                 prompt, schema, cfg.run.max_chars)
        out: List[Dict] = []
        queue: List[Dict] = []
        for iid in batch:
            row: Dict = {"interaction_id": iid, "model": cfg.models.judge,
                         "run_ts": run_ts()}
            for role in roles:
                p = role["prefix"]
                hit = results.get(p, {}).get(iid)
                if hit is None:
                    continue
                text_value, res = hit
                corrected = res.get("corrected_category")
                if corrected in (None, "null", "", "None"):
                    corrected = None
                needs_review = bool(res.get(const.NEEDS_REVIEW, False))
                row[f"{p}_text"] = text_value
                row[f"{p}_{const.OTHER_CORRECT}"] = bool(res.get(const.OTHER_CORRECT, True))
                row[f"{p}_corrected_category"] = corrected
                row[f"{p}_reason_theme"] = res.get("reason_theme", "")
                row[f"{p}_{const.NEEDS_REVIEW}"] = needs_review
                # The stronger model is unsure -> HITL queue (Step 4).
                if needs_review:
                    queue.append(hitl_queue.make_row(
                        iid, p, "audit", text_value, corrected or const.OTHER, None, res.get("reason_theme", "")))
            out.append(row)
        # Checkpoint each batch so a crash doesn't lose the whole run's work.
        written += store.append(cfg.tables.audit, out)
        miscategorized += sum(1 for o in out for r in roles
                              if o.get(f'{r["prefix"]}_{const.OTHER_CORRECT}') is False)
        queued += hitl_queue.enqueue(store, cfg, queue)
        logger.info("[step3] audited %d/%d interactions (%d roles miscategorized, %d -> HITL queue)",
                    written, len(todo), miscategorized, queued)

    return written