"""Test helpers (no pytest dependency): build a Config from the repo's real
config.example.yaml + taxonomy.yaml, a temp SQLite store, and source-schema rows.

Keeping these pytest-free means they can also be reused from plain scripts.
"""
from pathlib import Path

import pandas as pd

from hire_pipeline.config import load_config
from hire_pipeline.store import SQLStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_cfg(tmp_dir):
    """Load the shipped example config, resolving the real taxonomy.yaml."""
    text = (REPO_ROOT / "config.example.yaml").read_text(encoding="utf-8")
    text = text.replace("taxonomy_file: taxonomy.yaml",
                        f"taxonomy_file: {REPO_ROOT / 'taxonomy.yaml'}")
    cfg_path = Path(tmp_dir) / "config.yaml"
    cfg_path.write_text(text, encoding="utf-8")
    return load_config(str(cfg_path))


def make_store(tmp_dir):
    """A real SQLite database in a temp file.

    Deliberately a file rather than :memory: — an in-memory SQLite database is
    per-connection, so it would hide bugs where a step expects a write to be
    visible to a later read.
    """
    return SQLStore(f"sqlite:///{Path(tmp_dir) / 'hire_test.db'}")


def interaction(iid, conv, turn, *, date="2024-01-01", user_input="",
                agent_output="", control=None, action=None):
    """One row in the raw source schema (matches the fraud-agent dataset CSV)."""
    return {
        "interaction_id": iid,
        "conversation_id": conv,
        "turn": turn,
        "event_date": date,
        "event_time": "10:00:00",
        "user_input": user_input,
        "agent_output": agent_output,
        "user_input_type": "quick_reply" if control else "free_text",
        "agent_response_type": "action" if action else "free_text",
        "user_control_id": control,
        "agent_action_id": action,
    }


def seed_source(store, cfg, rows):
    store.write(cfg.tables.source, pd.DataFrame(rows))
