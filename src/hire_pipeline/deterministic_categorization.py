"""Step 1: Deterministic telemetry.  "We label what we know."

Applies the deterministic routing maps (from taxonomy.yaml / cfg.taxonomy) to the
raw source table and writes a dedicated Step 1 table (deterministic): every row plus
the derived input_category / output_category (user and agent
deterministic categories) and, per conversation, resolution_status. The raw
source table is never mutated. Step 1 reads it and produces the labeled table.

It then computes the headline metric: deterministic coverage. No LLM. 
This is the cheap, drift-free layer and its metric trend is itself a product signal: 
a falling coverage rate means demand is drifting past the agent's contract.

The rules read the raw routing signals loaded by ingest (user_control_id,
agent_action_id). Interactions not covered by the rules get the freeform label
and flow to Step 2.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import pandas as pd

from .config import Config
from .store import Store, run_ts
from . import constants as const

logger = logging.getLogger("hire.step1")

def required_source_columns(cfg: Config) -> List[str]:
    """The source-table columns the pipeline reads, with who reads them.

    Checked at ingest so a schema mismatch fails at the boundary with one message
    naming everything that's missing, rather than as a KeyError several steps deep.
    """
    return [
        cfg.columns.interaction_id,    # every step keys on this
        cfg.columns.conversation_id,   # Step 1 resolution, Step 6 grouping
        cfg.columns.turn,              # Step 1 ordering, Step 6 turns-to-resolution
        cfg.columns.date,              # Step 1 coverage trend
        cfg.columns.input_text,        # Step 2 user-side residual
        cfg.columns.output_text,       # Step 2 agent-side residual, Step 6 red lines
        cfg.columns.user_signal,       # Step 1 user routing signal
        cfg.columns.agent_signal,      # Step 1 agent routing signal
    ]


def apply_rules(store: Store, cfg: Config) -> None:
    """Read the raw source table, apply the deterministic routing rules 
    and write the labeled Step 1 table (deterministic).

    The labeled table is fully refreshed from the raw source signals on every call,
    so re-running is safe and the raw source is left untouched. 
    This ensures that if the rules are updated, the new rules will be applied to all source rows on the next run.
    """
    src = cfg.tables.source
    det = cfg.tables.deterministic
    df = store.read(src).copy()
    if df.empty:
        logger.warning("Source table %s is empty — ingest a dataset first", src)
        return

    # ingest validates the full schema, but the table can also be populated by
    # other means (a warehouse view, a previous schema version), so don't index
    # the signal columns blind.
    user_signal, agent_signal = cfg.columns.user_signal, cfg.columns.agent_signal
    missing = [c for c in (user_signal, agent_signal) if c not in df.columns]
    if missing:
        raise ValueError(
            f"Source table {src} is missing the routing signal column(s) {missing}. "
            "These carry the id of the control the user tapped and the action the "
            "agent took: they are what Step 1 routes on. Rename them via the "
            "`columns` defaults in config.py if your telemetry calls them something "
            "else. See datasets/fraud-agent/DATASET.md for the source schema."
        )

    df[cfg.deterministic.input_category] = (
        df[user_signal].map(cfg.taxonomy.user_controls).fillna(cfg.deterministic.freeform_input_label)
    )
    df[cfg.deterministic.output_category] = (
        df[agent_signal].map(cfg.taxonomy.agent_actions).fillna(cfg.deterministic.freeform_output_label)
    )
    store.write(det, df)
    logger.info("Applied deterministic rules: %s -> %s (input & output categories)", src, det)


def resolve_conversation(intents: set, action_categories: set,
                         ended_via_control: bool,
                         resolving_actions: Dict[str, set]) -> str:
    """Derive a conversation's resolution_status from what the user wanted and what
    the agent did: all deterministic, no free-text parsing.

    Inputs:
      * intents: the set of user intent categories in the conversation.
        Navigation/closing labels can be included; they simply match no action.
      * action_categories: the set of agent action categories taken.
      * ended_via_control: whether the user closed with the end_conversation control.
      * resolving_actions: intent -> {actions that resolve it}, from cfg.taxonomy.

    Rules:
      * resolved: the agent took an action that matches a stated intent.
      * unresolved: a resolving action was expected but none matched, and the user
        formally closed (nothing that helped was done).
      * abandoned: a resolving action was expected but none matched, and the user
        did not formally close.
      * undetermined: no intent has a known resolving action (free-text intent, pure
        navigation, or an informational ask), so resolution can't be judged
        deterministically. Not counted as success or failure.
    """
    expected = set().union(*(resolving_actions.get(i, set()) for i in intents)) if intents else set()
    if not expected:
        return const.UNDETERMINED
    if action_categories & expected:
        return const.RESOLVED
    return const.UNRESOLVED if ended_via_control else const.ABANDONED


def derive_resolution(store: Store, cfg: Config) -> Dict[str, int]:
    """Derive each conversation's resolution_status from the input/output combination
    (see resolve_conversation) and save it.
    Run AFTER apply_rules (it reads the derived output-side categories).

    Deterministic, conversation-level: no LLM, no free-text parsing.
    Returns the resolved / unresolved / abandoned / undetermined conversation counts.
    """
    det = cfg.tables.deterministic
    conv = cfg.columns.conversation_id
    in_cat = cfg.deterministic.input_category
    out_cat = cfg.deterministic.output_category

    counts = dict.fromkeys(
        (const.RESOLVED, const.UNRESOLVED, const.ABANDONED, const.UNDETERMINED), 0)
    df = store.read(det)
    if df.empty:
        return counts

    free_in = cfg.deterministic.freeform_input_label
    free_out = cfg.deterministic.freeform_output_label
    resolution: Dict[str, str] = {}
    for cid, g in df.groupby(conv):   # groupby skips NaN conversation ids
        # user INTENT categories / agent ACTION categories taken (exclude freeform),
        # and whether the user closed via the end control
        intents = {v for v in g[in_cat] if pd.notna(v) and v != free_in}
        actions = {v for v in g[out_cat] if pd.notna(v) and v != free_out}
        ended = bool((g[in_cat] == const.END_CONVERSATION).any())
        status = resolve_conversation(intents, actions, ended,
                                      cfg.taxonomy.intent_resolving_actions)
        resolution[cid] = status
        counts[status] += 1

    df["resolution_status"] = df[conv].map(resolution)
    store.write(det, df)

    total = sum(counts.values()) or 1
    for status, n in counts.items():
        _snapshot(store, cfg, "resolution_status", status, n / total)
    logger.info("Derived resolution_status for %d conversations: %s", total, counts)
    return counts


def compute_coverage(store: Store, cfg: Config) -> Dict[str, Dict]:
    """Overall deterministic coverage for each role (user input, agent output),
    appending a snapshot per role. Returns {prefix: {total, covered, coverage}}."""
    df = store.read(cfg.tables.deterministic)
    out: Dict[str, Dict] = {}
    for role in cfg.roles():
        prefix, cat, freeform = role["prefix"], role["category_col"], role["freeform_label"]
        total = len(df)
        covered = int((df[cat] != freeform).sum()) if total else 0
        coverage = (covered / total) if total else 0.0
        logger.info("[step1/%s] deterministic coverage = %.3f (%d/%d)",
                    prefix, coverage, covered, total)
        _snapshot(store, cfg, f"{prefix}_deterministic_coverage", None, coverage)
        out[prefix] = {"total": total, "covered": covered, "coverage": coverage}
    return out


def coverage_trend(store: Store, cfg: Config, prefix: str = "input") -> List[Dict]:
    """Per-day deterministic-coverage series for one role (default user input)."""
    role = next(r for r in cfg.roles() if r["prefix"] == prefix)
    cat, freeform = role["category_col"], role["freeform_label"]
    date_col = cfg.columns.date

    df = store.read(cfg.tables.deterministic)
    if df.empty:
        return []

    out: List[Dict] = []
    for date_value, grp in df.groupby(date_col):
        total = len(grp)
        covered = int((grp[cat] != freeform).sum())
        out.append({
            "date_value": date_value,
            "total_rows": total,
            "deterministic_coverage": (covered / total) if total else 0.0,
        })
    return sorted(out, key=lambda r: str(r["date_value"]))


def freeform_residual(store: Store, cfg: Config, role: Dict) -> List[Dict]:
    """Interactions Step 1 could NOT label for this role: the input to Step 2 (LLM).
    'role' is a descriptor from 'cfg.roles()'."""
    content, cat, freeform = role["content_col"], role["category_col"], role["freeform_label"]

    df = store.read(cfg.tables.deterministic)
    if df.empty:
        return []

    mask = (df[cat] == freeform) & df[content].notna() & (df[content].astype(str).str.strip() != "")
    sub = df.loc[mask, [cfg.columns.interaction_id, content]]
    return [{"interaction_id": r[cfg.columns.interaction_id], "text_value": r[content]}
            for _, r in sub.iterrows()]


def _snapshot(store: Store, cfg: Config, metric: str, dimension, value: float) -> None:
    store.append(cfg.tables.metrics, [{
        "run_ts": run_ts(),
        "metric": metric,
        "dimension": dimension,
        "value": float(value),
    }])