"""Step 2 (cont.): low-confidence escalation to a stronger model.

Instead of sending low-confidence rows straight to a human, escalate them to a
stronger model for a second opinion (reusing the same confidence field and
threshold). Most rows stay cheap; only genuinely ambiguous ones pay for the
stronger model. Rows the stronger model is also unsure about are handed to the
Step 4 HITL queue. Those human corrections are the ground-truth feedback
that improves the prompt and the deterministic router.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from .config import Config
from .store import Store, run_ts, to_float
from .llm import LLMClient
from .llm_classify import classify_roles
from . import hitl_queue, prompts, constants as const

logger = logging.getLogger("hire.escalation")

def escalate_low_confidence(store: Store, cfg: Config, llm: LLMClient) -> int:
    """Re-adjudicate *_status="escalate" rows with the stronger judge model.

    For each role, low-confidence classifications get a second opinion, written to
    the escalation table's columns (one row per interaction). 
    Rows the judge is still unsure about are added to the HITL queue. 
    Returns the number of interactions escalated.
    """
    roles = cfg.roles()
    classified = store.read(cfg.tables.classified)
    if classified.empty:
        return 0
    already = store.ids(cfg.tables.escalation, "interaction_id")

    # per role, the rows flagged 'escalate': {prefix: {interaction_id: text}},
    # plus the cheap model's prior label for the re-check row.
    texts: Dict[str, Dict[str, str]] = {}
    prev: Dict[str, Dict[str, str]] = {}
    for role in roles:
        p = role["prefix"]
        status_col = f"{p}_status"
        if status_col not in classified.columns:
            continue
        for _, r in classified[classified[status_col] == const.ESCALATE].iterrows():
            iid = r["interaction_id"]
            if iid in already:
                continue
            texts.setdefault(p, {})[iid] = r.get(f"{p}_text")
            prev.setdefault(p, {})[iid] = r.get(f"{p}_category")
    todo = sorted({iid for m in texts.values() for iid in m})
    logger.info("[escalation] %d interactions with low-confidence roles to escalate", len(todo))
    if not todo:
        return 0

    prompt = {r["prefix"]: prompts.build_prompt(cfg, r["taxonomy_role"], cfg.run.language_hint,
                                                include_tone=r["tone"]) for r in roles}
    schema = {r["prefix"]: prompts.response_schema(include_tone=r["tone"]) for r in roles}
    threshold = cfg.run.confidence_threshold

    written = 0
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
                conf = to_float(res.get("confidence"))
                category = res.get("category", const.OTHER)
                reason = res.get("reason", "")
                row[f"{p}_category"] = category
                row[f"{p}_confidence"] = conf
                row[f"{p}_reason"] = reason
                row[f"{p}_prev_category"] = prev[p][iid]
                # Still unsure after the stronger model -> hand to a human.
                if conf < threshold:
                    queue.append(hitl_queue.make_row(iid, p, "escalation", text_value, category, conf, reason))
            out.append(row)
        # Checkpoint each batch so a crash doesn't lose the whole run's work.
        written += store.append(cfg.tables.escalation, out)
        queued += hitl_queue.enqueue(store, cfg, queue)
        logger.info("[escalation] escalated %d/%d interactions; %d role-flags -> HITL queue",
                    written, len(todo), queued)
    return written
