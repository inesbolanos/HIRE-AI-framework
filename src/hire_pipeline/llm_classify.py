"""Step 2: supervised LLM classification.  "We catch what we're missing."

Maps each freeform (Step-1-residual) message onto the EXISTING category list with
a cheap model. It returns: category / confidence / user tone / category reason.
Two outcomes:
  * known but missed  -> a routing gap; feeds the backlog, raises coverage.
  * unknown / other   -> the out-of-scope residual; flows to Step 3.

Both roles of an interaction are classified in one pass and written to a single
wide row: the user message into input_* columns, the agent reply into output_*
columns (only for whichever side Step 1 left as residual).

Rows below the confidence threshold are marked *_status="escalate" for a
stronger model second opinion (see escalation.py); whatever the stronger model
still can't resolve goes to the HITL queue. Cost-aware tiering: most rows stay
cheap; only ambiguous ones pay for the stronger model.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from .config import Config
from .store import Store, run_ts, to_float
from .llm import LLMClient
from . import prompts, deterministic_categorization as step1, constants as const

logger = logging.getLogger("hire.step2")


def classify_roles(llm: LLMClient, model: str, batch: List[str],
                   texts: Dict[str, Dict[str, str]], prompt: Dict[str, str],
                   schema: Dict[str, Dict], max_chars: int) -> Dict[str, Dict[str, tuple]]:
    """Classify one batch of interactions, one set-based call per role.

    `texts` maps role prefix -> {interaction_id -> raw text}; texts are truncated
    to max_chars. Returns {prefix -> {interaction_id -> (truncated text, result)}}.
    Shared by Steps 2/3 and the escalation pass, so every LLM step batches the
    same way: providers that can do set-based inference (a warehouse) turn each
    role's batch into a single SQL statement instead of one round trip per
    message; the default implementation still just loops, so every provider
    works unchanged.
    """
    results: Dict[str, Dict[str, tuple]] = {}
    for p, by_iid in texts.items():
        items = [(iid, (by_iid[iid] or "")[:max_chars])
                 for iid in batch if by_iid.get(iid) is not None]
        if not items:
            continue  # no interaction in this batch needs this role
        answers = llm.classify_batch(prompt[p], [t for _, t in items], schema[p],
                                     model=model)
        results[p] = {iid: (text, res)
                      for (iid, text), res in zip(items, answers)}
    return results


def classify(store: Store, cfg: Config, llm: LLMClient) -> int:
    """Classify the Step-1 residual of every interaction; write one wide row each.

    For each role (user input / agent output) the interaction's residual text is
    classified into that role's columns. Returns the number of interactions written. 
    Incremental: only interactions not already in the classified table are processed.
    """
    roles = cfg.roles()
    # residual text per role, keyed by interaction_id
    role_residual = {
        role["prefix"]: {r["interaction_id"]: r["text_value"]
                         for r in step1.freeform_residual(store, cfg, role)}
        for role in roles
    }
    already = store.ids(cfg.tables.classified, "interaction_id")
    todo = sorted({iid for m in role_residual.values() for iid in m} - already)
    n_msgs = sum(len(m) for m in role_residual.values())
    logger.info("[step2] %d residual messages, %d interactions new to classify", n_msgs, len(todo))
    if not todo:
        return 0

    prompt = {r["prefix"]: prompts.build_prompt(cfg, r["taxonomy_role"], cfg.run.language_hint,
                                                include_tone=r["tone"]) for r in roles}
    schema = {r["prefix"]: prompts.response_schema(include_tone=r["tone"]) for r in roles}
    threshold = cfg.run.confidence_threshold

    written = 0
    for start in range(0, len(todo), cfg.run.batch_size):
        batch = todo[start:start + cfg.run.batch_size]
        results = classify_roles(llm, cfg.models.classifier, batch, role_residual,
                                 prompt, schema, cfg.run.max_chars)

        rows: List[Dict] = []
        for iid in batch:
            row: Dict = {"interaction_id": iid, "model": cfg.models.classifier,
                         "run_ts": run_ts()}
            for role in roles:
                p = role["prefix"]
                hit = results.get(p, {}).get(iid)
                if hit is None:
                    continue  # this role wasn't residual for this interaction
                text_value, res = hit
                conf = to_float(res.get("confidence"))
                row[f"{p}_text"] = text_value
                row[f"{p}_category"] = res.get("category", const.OTHER)
                row[f"{p}_confidence"] = conf
                row[f"{p}_reason"] = res.get("reason", "")
                row[f"{p}_status"] = const.AUTO if conf >= threshold else const.ESCALATE
                if role["tone"]:
                    row[f"{p}_tone"] = res.get("tone")
            rows.append(row)
        written += store.append(cfg.tables.classified, rows)
        logger.info("[step2] wrote %d/%d interactions", written, len(todo))

    return written
