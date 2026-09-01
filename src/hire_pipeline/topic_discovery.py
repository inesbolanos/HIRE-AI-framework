"""Step 5: semi-unsupervised discovery.  "We discover what we don't know."

Consolidates the confirmed 'other' USER messages from Step 3 into named, emergent
topics. Discovery runs on the user side only. Rather than let the LLM
group themes (not reproducible), we cluster the messages with embeddings + HDBSCAN
(BERTopic), which gives reproducible boundaries and an objective quality signal, and
use the LLM only to name each cluster.

Assignments are written to the topic_map table as 'input_topic_id' /
'input_topic_label' columns, one row per interaction.

BERTopic is optional; if it (or embeddings) isn't available, this step is skipped
with a clear log message and the rest of the pipeline still runs.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List

import numpy as np
import pandas as pd

from .config import Config
from .store import Store, run_ts, truthy
from .llm import LLMClient, LLMError, parse_json
from . import prompts, constants as const

logger = logging.getLogger("hire.step5")

# Discovery operates on the user side (unmet-demand discovery).
PREFIX = "input"


def discover_topics(store: Store, cfg: Config, llm: LLMClient, refit: bool = False) -> int:
    """Cluster confirmed 'other' user messages and name each cluster.

    INCREMENTAL by default: the fitted model is persisted; normal runs assign only
    NEW confirmed 'other' messages to existing topics via transform() so topic ids
    and labels stay stable. refit=True (or first run) re-fits from scratch. When
    the outlier share grows past refit_outlier_threshold, it's time to refit.
    """
    try:
        from bertopic import BERTopic
    except ImportError:
        logger.warning("[step5] bertopic not installed; skipping topic discovery "
                       "(pip install bertopic umap-learn hdbscan)")
        return 0

    audit_df = store.read(cfg.tables.audit)
    other_correct_col = f"{PREFIX}_{const.OTHER_CORRECT}"
    needs_review_col = f"{PREFIX}_{const.NEEDS_REVIEW}"
    text_col = f"{PREFIX}_text"
    if audit_df.empty or other_correct_col not in audit_df.columns or text_col not in audit_df.columns:
        logger.info("[step5] no audited user 'other' rows yet; run Step 3 audit first")
        return 0

    model_path = os.path.join(cfg.discovery.model_dir, "bertopic")
    have_model = (not refit and os.path.exists(model_path)
                  and store.has(cfg.tables.topics)
                  and store.has(cfg.tables.topic_map))

    # Eligible = confirmed 'other' with non-empty text, excluding rows the audit
    # flagged for a human (needs_review): those are pending, not settled.
    eligible_mask = (
        audit_df[other_correct_col].apply(truthy)
        & audit_df[text_col].notna()
        & (audit_df[text_col].astype(str).str.strip() != "")
    )
    if needs_review_col in audit_df.columns:
        eligible_mask &= ~audit_df[needs_review_col].apply(truthy)
    eligible = audit_df[eligible_mask]
    # Incremental = only interactions not already assigned to a topic.
    if have_model:
        assigned = store.ids(cfg.tables.topic_map, "interaction_id")
        eligible = eligible[~eligible["interaction_id"].isin(assigned)]

    ids = eligible["interaction_id"].tolist()
    docs = eligible[text_col].tolist()
    if not ids:
        logger.info("[step5] no new confirmed 'other' messages to cluster")
        return 0

    if not have_model and len(ids) < cfg.discovery.cluster_min_size * 2:
        logger.info("[step5] too few confirmed 'other' messages (%d) to fit topics", len(ids))
        return 0

    try:
        embeddings = llm.embed(docs)
    except LLMError as e:
        logger.warning("[step5] embeddings unavailable (%s); skipping clustering", e)
        return 0

    emb = np.array(embeddings)

    # incremental: assign to existing topics, reuse labels
    if have_model:
        topic_model = BERTopic.load(model_path)
        topics, _ = topic_model.transform(docs, embeddings=emb)
        topics_df = store.read(cfg.tables.topics)
        label_map = {int(r["topic_id"]): r["topic_label"] for _, r in topics_df.iterrows()}
        store.append(cfg.tables.topic_map, _assignment_rows(ids, topics, label_map))
        n_out = sum(1 for t in topics if int(t) == -1)
        frac = n_out / len(ids)
        logger.info("[step5] assigned %d new msgs (%d outliers, %.1f%%)", len(ids), n_out, 100 * frac)
        if frac > cfg.discovery.refit_outlier_threshold:
            logger.warning("[step5] outlier rate %.1f%% > %.0f%% — rerun with refit=True",
                           100 * frac, 100 * cfg.discovery.refit_outlier_threshold)
        return len(ids)

    # fit (first run / refit): build, name, overwrite, save
    from umap import UMAP
    from hdbscan import HDBSCAN
    umap_model = UMAP(n_neighbors=cfg.discovery.umap_n_neighbors, n_components=5,
                      min_dist=0.0, metric="cosine", random_state=cfg.discovery.umap_seed)
    hdbscan_model = HDBSCAN(min_cluster_size=cfg.discovery.cluster_min_size,
                            min_samples=cfg.discovery.hdbscan_min_samples,
                            metric="euclidean", cluster_selection_method="eom",
                            prediction_data=True)
    topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model,
                           calculate_probabilities=False, verbose=False)
    topics, _ = topic_model.fit_transform(docs, embeddings=emb)
    info = topic_model.get_topic_info()
    n_topics = len([t for t in info["Topic"].tolist() if int(t) != -1])
    logger.info("[step5] BERTopic fit %d topics over %d messages", n_topics, len(ids))

    labels = _name_topics(cfg, llm, topic_model, info, docs, topics)

    stamp = run_ts()
    summary = []
    for _, r in info.iterrows():
        tid = int(r["Topic"])
        kws = "" if tid == -1 else ", ".join(w for w, _ in topic_model.get_topic(tid)[:10])
        summary.append({"topic_id": tid,
                        "topic_label": labels[tid],  # _name_topics covers every tid in info
                        "size": int(r["Count"]), "keywords": kws, "run_ts": stamp})
    store.write(cfg.tables.topics, pd.DataFrame(summary))

    label_map = {t["topic_id"]: t["topic_label"] for t in summary}
    store.write(cfg.tables.topic_map, pd.DataFrame(_assignment_rows(ids, topics, label_map)))

    os.makedirs(cfg.discovery.model_dir, exist_ok=True)
    topic_model.save(model_path, serialization="pickle")
    logger.info("[step5] wrote %d topics, %d assignments, saved model", len(summary), len(ids))
    return len(ids)


def _name_topics(cfg, llm, topic_model, info, docs, topics) -> Dict[int, str]:
    """Use the LLM to name each non-outlier cluster (labels only)."""
    labels: Dict[int, str] = {-1: "outliers"}
    for tid in [int(t) for t in info["Topic"].tolist() if int(t) != -1]:
        keywords = [w for w, _ in topic_model.get_topic(tid)[:10]]
        samples = [d for d, t in zip(docs, topics) if int(t) == tid][:8]
        prompt = prompts.build_topic_naming_prompt(cfg, keywords, samples)
        fallback = f"topic_{tid}"
        try:
            res = llm.complete(prompt, model=cfg.models.judge)
            labels[tid] = parse_json(res).get("label") or fallback
        except Exception as e:
            logger.warning("[step5] could not name topic %d (%s: %s); using %r",
                           tid, type(e).__name__, e, fallback)
            labels[tid] = fallback
    return labels


def _assignment_rows(ids, topics, label_map) -> List[Dict]:
    """Build per-interaction topic assignment rows (input_topic_* columns)."""
    stamp = run_ts()
    rows = []
    for _id, t in zip(ids, topics):
        tid = int(t)
        rows.append({"interaction_id": _id,
                     "input_topic_id": tid,
                     "input_topic_label": label_map.get(tid, "outliers" if tid == -1 else f"topic_{tid}"),
                     "run_ts": stamp})
    return rows
