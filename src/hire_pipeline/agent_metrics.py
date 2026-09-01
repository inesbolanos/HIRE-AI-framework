"""Step 6: Agent metrics.  "We measure how the agent actually performs."

Deterministic evaluation of the five H.I.R.E. AI agent metrics over already-processed interactions.

It reads the Step 1 deterministic table (structure + resolution + structured
categories) and the Step 2 classified table (LLM intent, tone, agent response
category), writes one flag row per conversation to the conversation_metrics table
(so you can drill into exactly which conversations feed each metric), and appends
the aggregate rates to the metrics time-series.

Definitions (the category/tone sets and red-line regexes live in taxonomy.yaml ->
metrics, so they adapt per agent):

  * red_line_rate:              share of interactions where the agent did something unsafe: 
                                an output category in red_line_categories (e.g. overpromise) or 
                                the reply text matches a red_line_pattern.

  * user_correction_rate:       share of conversations where the user corrected the agent.

  * instant_resolution_rate:    from those conversations with an actionable request, the share
                                the agent resolved on the first exchange.

  * ping_pong_rate:             average turns to get the answer/action (over resolved conversations).

  * diy_rate:                   share of conversations abandoned, or where the user was
                                frustrated / asked for a human without being resolved.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import pandas as pd

from .config import Config
from .store import Store, run_ts
from . import constants as const

logger = logging.getLogger("hire.step6")

# The Step 2 columns this step reads. Their names come from the role prefixes in
# Config.roles() ("input" / "output"), which are code, not config — so unlike the
# Step 1 column names these are fixed and can be matched on literally.
_LLM_COLS = ("input_category", "output_category", "input_tone")


def _enrich(store: Store, cfg: Config) -> pd.DataFrame:
    """One per-interaction frame merging Step 1 (structure/actions) and
    Step 2 (LLM intent/tone/category), with effective columns the metrics read."""
    det = store.read(cfg.tables.deterministic)
    if det.empty:
        return det

    # Pull in only the Step 2 columns the metrics need, under an explicit llm_
    # prefix. The rename has to happen here rather than via merge(suffixes=...):
    # pandas only applies a suffix on a name COLLISION, so the LLM signal used to
    # disappear the moment deterministic.input_category was renamed away from
    # Step 2's fixed 'input_category' — silently, with every LLM-dependent metric
    # reading zero on a run that reported success.
    cls = store.read(cfg.tables.classified)
    present = ([c for c in _LLM_COLS if c in cls.columns]
               if not cls.empty and "interaction_id" in cls.columns else [])
    if not cls.empty and not present:
        logger.warning(
            "[step6] %s has none of %s, so user_correction_rate, category-based "
            "red lines and tone will read zero. Has Step 2 written this table?",
            cfg.tables.classified, list(_LLM_COLS))
    if present:
        slim = cls[["interaction_id"] + present].rename(
            columns={c: f"llm_{c}" for c in present})
        df = det.merge(slim, on="interaction_id", how="left")
    else:
        df = det.copy()

    in_cat, out_cat = cfg.deterministic.input_category, cfg.deterministic.output_category
    freeform_in = cfg.deterministic.freeform_input_label
    action_cats = set(cfg.taxonomy.agent_actions.values())

    def _col(name: str) -> pd.Series:
        """The column if Step 2 supplied it, otherwise an all-None column."""
        return df[name] if name in df.columns else pd.Series(None, index=df.index, dtype=object)

    # effective user intent: the LLM label for free-text residual, else the deterministic one
    df["eff_intent"] = [(li if (di == freeform_in and pd.notna(li)) else di)
                        for di, li in zip(df[in_cat], _col("llm_input_category"))]
    # structured agent action actually taken (deterministic output category, if a real action)
    df["agent_action"] = [a if a in action_cats else None for a in df[out_cat]]
    # LLM agent response category (for red-line categories like overpromise)
    df["llm_output_cat"] = _col("llm_output_category")
    df["tone"] = _col("llm_input_tone")
    return df


def evaluate_metrics(store: Store, cfg: Config) -> Dict[str, float]:
    """Compute the five metrics deterministically; write per-conversation flags and
    aggregate snapshots. Returns the aggregate rates."""
    df = _enrich(store, cfg)
    if df is None or df.empty:
        logger.warning("[step6] no deterministic table yet; run ingest + Step 1 first")
        return {}

    t = cfg.taxonomy
    resolving = t.intent_resolving_actions
    red_line_cats = set(t.red_line_categories)
    patterns = [re.compile(p, re.IGNORECASE) for p in t.red_line_patterns]
    correction_cats = set(t.correction_categories)
    frustration_tones = set(t.frustration_tones)
    escalation_cats = set(t.escalation_categories)
    out_text_col = cfg.columns.output_text
    conv_col = cfg.columns.conversation_id
    turn_col = cfg.columns.turn

    # "Instant" means the resolving action landed on the FIRST exchange, which is
    # read literally as turn == first_turn. Warn rather than silently score every
    # conversation as non-instant if the data is 0-indexed or otherwise offset.
    first_turn = int(pd.to_numeric(df[turn_col], errors="coerce").min())
    if first_turn != 1:
        logger.warning(
            "[step6] %r starts at %d, not 1. Treating %d as the first exchange so "
            "instant_resolution_rate stays meaningful — but the pipeline expects "
            "1-indexed turns, so check the source data.",
            turn_col, first_turn, first_turn)

    # interaction-level: red line (unsafe agent behaviour)
    def _red_line(row) -> bool:
        cat = row.get("llm_output_cat")
        if isinstance(cat, str) and cat in red_line_cats:
            return True
        text = str(row.get(out_text_col) or "")
        return any(p.search(text) for p in patterns)

    df["red_line"] = df.apply(_red_line, axis=1)
    total_interactions = len(df)
    red_line_interactions = int(df["red_line"].sum())

    # per-conversation flags
    rows: List[Dict] = []
    for conv_id, g in df.groupby(conv_col):
        g = g.sort_values(turn_col)
        intents = [i for i in g["eff_intent"].tolist() if pd.notna(i)]
        actionable = [i for i in intents if resolving.get(i)]
        resolving_union = set().union(*(resolving[i] for i in actionable)) if actionable else set()
        actions = [a for a in g["agent_action"].tolist() if pd.notna(a) and a]
        resolved = bool(set(actions) & resolving_union)

        # first turn (g is turn-sorted) where a resolving action landed
        hits = g[g["agent_action"].isin(resolving_union)]
        turn_to_res: Optional[int] = int(hits[turn_col].iloc[0]) if not hits.empty else None

        ended = const.END_CONVERSATION in intents
        frustration = any(str(x) in frustration_tones for x in g["tone"].tolist())
        escalation = any(i in escalation_cats for i in intents)
        rows.append({
            "conversation_id": conv_id,
            "turns": int(g[turn_col].max()),
            "turns_to_resolution": turn_to_res,                       # None if never resolved
            "resolvable": bool(actionable),                          # had an actionable request
            "resolved": resolved,
            "instant_resolution": bool(resolved and turn_to_res == first_turn),
            "user_correction": any(i in correction_cats for i in intents),
            "red_line": bool(g["red_line"].any()),
            "frustration": frustration,
            "escalation": escalation,
            # DIY: dropped without resolution, or frustrated/escalated without resolution
            "diy": not resolved and (not ended or frustration or escalation),
            "run_ts": run_ts(),
        })

    conv = pd.DataFrame(rows)
    store.write(cfg.tables.conversation_metrics, conv)

    # aggregate rates
    n = len(conv)
    resolvable = conv[conv["resolvable"]]
    resolved_conv = conv[conv["resolved"]]
    rates = {
        "red_line_rate": (red_line_interactions / total_interactions) if total_interactions else 0.0,
        "user_correction_rate": (int(conv["user_correction"].sum()) / n) if n else 0.0,
        "instant_resolution_rate": (int(resolvable["instant_resolution"].sum()) / len(resolvable)) if len(resolvable) else 0.0,
        "ping_pong_rate": float(resolved_conv["turns_to_resolution"].mean()) if len(resolved_conv) else 0.0,
        "diy_rate": (int(conv["diy"].sum()) / n) if n else 0.0,
    }
    store.append(cfg.tables.metrics, [
        {"run_ts": run_ts(), "metric": k, "dimension": None, "value": float(v)} for k, v in rates.items()
    ])
    logger.info("[step6] %s", ", ".join(f"{k}={v:.3f}" for k, v in rates.items()))
    return rates
