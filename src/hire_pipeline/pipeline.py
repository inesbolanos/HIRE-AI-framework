"""Orchestrator + CLI.

Wires the pipeline stages together and appends metric snapshots (deterministic
coverage and resolution-status mix) so they're tracked as a time series. Run on a
schedule; the trend is the signal.

Tables are pandas DataFrames saved as database tables: your data warehouse,
or a local SQLite file when you just want to try it out.

Commands:
    ingest    load the source CSV and apply Step 1 routing rules
    run       Step 1 rules -> Step 2 classify + escalate -> Step 3 audit
              -> Step 4 HITL queue -> Step 5 cluster -> Step 6 agent metrics

    evaluate       score the LLM layers against a gold set
    metrics        print the latest per-day deterministic-coverage series
    agent-metrics  compute the agent metrics (red-line / correction / instant-
                   resolution / ping-pong / DIY) deterministically — no API key
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

import pandas as pd

from .config import load_config, Config
from .store import Store, SQLStore
from .llm import LLMClient, LLMError, WarehouseClient
from . import deterministic_categorization as step1
from . import llm_classify as step2
from . import audit as step3
from . import topic_discovery as step5
from . import agent_metrics as step6
from . import escalation, evaluation

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("hire.pipeline")


def load_source(store: Store, cfg: Config, path: str) -> int:
    """Load the source CSV straight into the source table.

    The dataset file is already written in the source schema (see the fraud-agent
    generator), so there is no transformation step: this is a direct read.
    """
    if not os.path.isfile(path):
        raise ValueError(
            f"Source data file not found: {path}\n"
            "Pass --data with the path to your source CSV, or generate the bundled "
            "sample:\n  python datasets/fraud-agent/generate_sample_data.py"
        )
    df = pd.read_csv(path)

    missing = [c for c in step1.required_source_columns(cfg) if c not in df.columns]
    if missing:
        raise ValueError(
            f"{os.path.basename(path)} is missing required column(s): {missing}\n"
            f"Found: {sorted(df.columns)}\n"
            "Most names come from the `columns` block in config.py; the two routing "
            "signals (user_control_id / agent_action_id) and `turn` are fixed. The "
            "source schema is documented in datasets/fraud-agent/DATASET.md."
        )

    n = store.write(cfg.tables.source, df)
    logger.info("Loaded %d interactions -> %s", n, cfg.tables.source)
    return n


def _make_store(cfg: Config, url_override: Optional[str] = None) -> Store:
    """Build the table backend: the pipeline's tables are database tables.

    The URL comes from the environment variable named by storage.url_env, falling
    back to storage.default_url (a local SQLite file) so the sample data runs with
    no server and no credentials. Point it at your warehouse (the same one running
    the LLM layers) and data and model share a platform.
    """
    from sqlalchemy.exc import ArgumentError, NoSuchModuleError  # lazy, like store.py

    url = url_override or cfg.store_url
    if not url:
        raise RuntimeError(
            f"No database URL for the pipeline's tables. Set {cfg.storage.url_env} "
            "to a SQLAlchemy URL (your warehouse, or sqlite:///hire.db for a local "
            "file), or set storage.default_url in config.yaml."
        )
    try:
        return SQLStore(url, schema=cfg.storage.schema or None)
    except NoSuchModuleError as e:
        raise RuntimeError(
            f"No SQLAlchemy dialect for that database URL: {e}\n"
            "Install your platform's DIALECT, not just its DBAPI driver:\n"
            "  Databricks   pip install databricks-sqlalchemy\n"
            "  Snowflake    pip install snowflake-sqlalchemy\n"
            "  Postgres     pip install psycopg\n"
            "SQLite needs nothing beyond SQLAlchemy itself."
        ) from e
    except ArgumentError as e:
        raise RuntimeError(
            f"Could not parse that database URL: {e}\n"
            "Expected a SQLAlchemy URL, for example:\n"
            "  sqlite:///hire.db\n"
            "  databricks://token:<pat>@<host>?http_path=<path>&catalog=<c>&schema=<s>"
        ) from e


def _make_llm(cfg: Config) -> LLMClient:
    """Build the LLM client for the configured provider (models.provider).

    Steps 1 and 6 never come here: they are deterministic and need no model at
    all. Only Steps 2-5 do, and they run inside your warehouse, so the workspace
    entitlement is the authentication.
    """
    provider = (cfg.models.provider or "warehouse").strip().lower()

    if provider != "warehouse":
        raise RuntimeError(
            f"Unknown models.provider {cfg.models.provider!r}. This repository ships "
            "the 'warehouse' provider, which runs the model through your data "
            "warehouse's own SQL function.\nTo use a different backend, implement "
            "classify() on hire_pipeline.llm.LLMClient and pass an instance:\n"
            "    pipeline.run(cfg, store, llm=MyClient())"
        )

    if not cfg.models.sql_template:
        raise RuntimeError(
            "models.sql_template is empty: steps 2-5 need your platform's LLM "
            "function. Uncomment the block for your platform in config.yaml:\n"
            "  Databricks:  ai_query('{model}', {input})\n"
            "  Snowflake:   SNOWFLAKE.CORTEX.COMPLETE('{model}', {input})\n"
            "Any scalar SQL function of the form FN(model, prompt) works: see the "
            "README table 'Running it in your data warehouse'.\n"
            "Steps 1 and 6 ('ingest', 'metrics', 'agent-metrics') need no model at all."
        )

    missing = [n for n, v in (("classifier", cfg.models.classifier),
                              ("judge", cfg.models.judge)) if not v]
    if missing:
        raise RuntimeError(
            f"models.{' and models.'.join(missing)} not set: Steps 2-5 need the "
            "model or endpoint names as your platform spells them (the cheap "
            "'classifier' for the first pass, the stronger 'judge' for escalation, "
            "the 'other' audit and topic naming). See config.example.yaml for the "
            "names each platform uses."
        )

    if not cfg.sql_url:
        raise RuntimeError(
            f"{cfg.models.sql_url_env} is not set: Steps 2-5 connect to your "
            "warehouse to run the model there. Set it to a SQLAlchemy URL for your "
            "platform.\nSteps 1 and 6 need no connection at all: 'ingest', 'metrics' "
            "and 'agent-metrics' give you deterministic coverage, resolution status "
            "and all five agent metrics with no credentials whatsoever."
        )

    return WarehouseClient(
        url=cfg.sql_url,
        classifier_model=cfg.models.classifier,
        judge_model=cfg.models.judge,
        sql_template=cfg.models.sql_template,
        max_retries=cfg.run.max_retries,
        batch_size=cfg.run.batch_size,
    )


def _run_step1(store: Store, cfg: Config) -> None:
    """Step 1: routing rules, resolution status, coverage — deterministic, no LLM."""
    step1.apply_rules(store, cfg)
    step1.derive_resolution(store, cfg)
    step1.compute_coverage(store, cfg)


def run(cfg: Config, store: Store, refit: bool = False,
        llm: Optional[LLMClient] = None) -> None:
    """Run Steps 1-6.

    `llm` defaults to the client for the configured provider (models.provider).
    Pass your own LLMClient to use a backend this repo doesn't ship — a hosted
    API, a local model, or BigQuery's table-valued ML.GENERATE_TEXT — without
    editing the pipeline. This is the injection point llm.py's docstring refers to.
    """
    llm = llm or _make_llm(cfg)

    logger.info("=== Step 1: deterministic telemetry ===")
    _run_step1(store, cfg)

    logger.info("=== Step 2: supervised classification ===")
    step2.classify(store, cfg, llm)

    logger.info("=== Step 2 (cont.): escalate low-confidence to stronger model ===")
    escalation.escalate_low_confidence(store, cfg, llm)

    logger.info("=== Step 3: audit 'other' + free-form themes ===")
    step3.audit_other(store, cfg, llm)

    logger.info("=== Step 5: cluster + name emergent topics ===")
    step5.discover_topics(store, cfg, llm, refit=refit)

    logger.info("=== Step 6: agent metrics ===")
    step6.evaluate_metrics(store, cfg)

    logger.info("Pipeline complete")


def evaluate(cfg: Config, store: Store, gold_path: str,
             target_precision: float = 0.9) -> dict:
    """Score the user-intent classification (input_category) against the gold set."""
    gold_rows = evaluation.load_gold(gold_path)
    gold_map = {g["interaction_id"]: g["gold_category"] for g in gold_rows}

    df = store.read(cfg.tables.classified)
    if df.empty or "input_category" not in df.columns:
        logger.warning(
            "Nothing to evaluate yet: the classified table (%s) is empty. The gold "
            "set scores the LLM layers: run the full pipeline first "
            "(`hire run`, which needs your warehouse connection), then re-run "
            "evaluate.", cfg.tables.classified)
        return {"score": {"n": 0}, "calibration": None}

    sub = df[df["input_category"].notna()]
    fit_rows = [{"interaction_id": r["interaction_id"],
                 "category": r["input_category"],
                 "confidence": r.get("input_confidence")}
                for r in sub.to_dict("records")]
    predictions = {r["interaction_id"]: r["category"] for r in fit_rows}

    result = evaluation.score(predictions, gold_rows)
    calib = evaluation.calibrate_threshold(fit_rows, gold_map, target_precision)

    logger.info("Gold-set score: n=%d accuracy=%.3f false_other=%.3f false_known=%.3f",
                result["n"], result["accuracy"],
                result["false_other_rate"], result["false_known_rate"])
    logger.info("Threshold calibration: chosen=%.2f meets_target(%.2f)=%s",
                calib["chosen_threshold"], target_precision, calib["meets_target"])
    return {"score": result, "calibration": calib}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="hire", description="H.I.R.E. agent-eval pipeline")
    p.add_argument("command", choices=["ingest", "run", "evaluate", "metrics", "agent-metrics"])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--data", default="datasets/fraud-agent/sample_fraud_agent_conversations.csv",
                   help="source CSV (already in the source schema) to load into the source table")
    p.add_argument("--store-url", default=None,
                   help="SQLAlchemy URL for the pipeline's tables (overrides the "
                        "environment variable named by storage.url_env)")
    p.add_argument("--gold", default="datasets/fraud-agent/gold_set.example.csv")
    p.add_argument("--refit", action="store_true", help="Step 5: refit BERTopic from scratch")
    p.add_argument("--target-precision", type=float, default=0.9)
    args = p.parse_args(argv)

    try:
        cfg = load_config(args.config)
        store = _make_store(cfg, args.store_url)

        if args.command == "ingest":
            load_source(store, cfg, args.data)
            _run_step1(store, cfg)  # routing rules so coverage/residual are ready
        elif args.command == "run":
            run(cfg, store, refit=args.refit)
        elif args.command == "evaluate":
            evaluate(cfg, store, args.gold, args.target_precision)
        elif args.command == "metrics":
            for row in step1.coverage_trend(store, cfg):
                print(row)
        elif args.command == "agent-metrics":
            # deterministic: reads existing tables, no LLM needed
            for k, v in step6.evaluate_metrics(store, cfg).items():
                print(f"{k}: {v:.3f}")
    except (RuntimeError, LLMError, ValueError) as e:
        # Missing config or connectivity are expected user situations, not bugs:
        # show the guidance, not a stack trace.
        print(f"\n{e}\n", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
