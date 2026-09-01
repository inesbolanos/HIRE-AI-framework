"""Storage layer: the pipeline's tables live in a database.

Every "table" in the H.I.R.E. AI framework is a pandas DataFrame, persisted by
'SQLStore' through SQLAlchemy, so the same code writes to your data warehouse
(Databricks, Snowflake, Postgres, …) or, with no server and no credentials, to a
local SQLite file.

Reads materialise a SELECT into a DataFrame and writes turn it back into SQL.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pandas as pd

logger = logging.getLogger("hire.store")


def run_ts() -> str:
    """The UTC timestamp every step stamps its rows with."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def truthy(value) -> bool:
    """Coerce a value that may have round-tripped through the database as 0/1 or
    "true"/"false" back into a bool. Used when filtering boolean columns after a
    reload: SQLite has no native boolean type, and warehouse drivers differ."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "t"}


def to_float(value, default: float = 0.0) -> float:
    """Coerce a possibly-missing/str value (e.g. an LLM confidence) to float,
    falling back to 'default' on None or unparseable input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Store(ABC):
    """The storage contract the pipeline steps call.

    Table 'name' values are the logical names from config (e.g.
    'step2_llm_classified'). 'read' MUST return an empty DataFrame (not raise) for
    a table that does not exist yet.
    """

    @abstractmethod
    def has(self, name: str) -> bool:
        """True if the table exists."""

    @abstractmethod
    def read(self, name: str) -> pd.DataFrame:
        """Return the whole table as a DataFrame (empty DataFrame if it doesn't exist)."""

    @abstractmethod
    def write(self, name: str, df: pd.DataFrame) -> int:
        """Overwrite the table with 'df' and persist it. Returns the row count."""

    @abstractmethod
    def append(self, name: str, rows: Sequence[Dict]) -> int:
        """Append dict rows to a table (creating it if needed). Returns rows added."""

    @abstractmethod
    def ids(self, name: str, column: str = "interaction_id") -> set:
        """Return the set of values in 'column' (empty if the table/column is absent).

        Used by the incremental steps to skip interactions already processed. Every
        table is keyed by 'interaction_id' alone (one row per interaction)."""


class SQLStore(Store):
    """The pipeline's tables, as real tables in a database.

    Configured entirely in config.yaml — no code needed:

        storage:
          url_env: HIRE_STORE_URL   # env var with the SQLAlchemy URL
          schema:  analytics        # optional: where to create the tables

    Point ``url_env`` at your **data warehouse** (Databricks, Snowflake, Postgres…)
    and, if the LLM layers run there too, the data and the model share one platform
    and nothing has to leave it. With no warehouse, a local **SQLite** file is still
    a real database and needs no server and no credentials: same code path, so a
    trial run and a production run differ only by connection string.

    Requires SQLAlchemy plus your platform's driver (``pip install -e '.[sql]'``);
    SQLite needs only SQLAlchemy.

    Reads hit the database each time (no cache), so writes are immediately visible
    to later reads in the same run.

    Note on ``write()``: it replaces the table wholesale (drop + recreate), which is
    what a full-refresh step means here. On a governed warehouse that can discard
    grants or table properties, so point ``schema`` at a working schema you own
    rather than a curated one.
    """

    def __init__(self, url: str, schema: Optional[str] = None, engine=None):
        if engine is not None:                     # injected (tests, or your own)
            self.engine = engine
        else:
            try:
                from sqlalchemy import create_engine
            except ImportError as e:  # pragma: no cover
                raise ImportError(
                    "pip install -e '.[sql]' (plus your platform's driver; SQLite "
                    "needs nothing extra) to store the pipeline's tables"
                ) from e
            if not url:
                raise ValueError(
                    "No database URL. Set the environment variable named by "
                    "storage.url_env — e.g. sqlite:///hire.db for a local file, or "
                    "your warehouse's SQLAlchemy URL."
                )
            self.engine = create_engine(url, future=True)
        self.schema = schema or None
        logger.info("SQLStore ready (dialect: %s, schema: %s)",
                    self.engine.dialect.name, self.schema or "<default>")

    def has(self, name: str) -> bool:
        from sqlalchemy import inspect
        return inspect(self.engine).has_table(name, schema=self.schema)

    def read(self, name: str) -> pd.DataFrame:
        if not self.has(name):
            return pd.DataFrame()
        # A plain SELECT is more portable across warehouse dialects than
        # read_sql_table, which needs full metadata reflection.
        return pd.read_sql_query(f"SELECT * FROM {self._q(name)}", self.engine)

    def write(self, name: str, df: pd.DataFrame) -> int:
        if df.columns.empty:
            raise ValueError(
                f"Refusing to write table {name!r} from a DataFrame with no columns. "
                "The step that produced it found nothing to write: check its input."
            )
        # if_exists="replace" drops & recreates the table to mirror a full overwrite.
        df.reset_index(drop=True).to_sql(name, self.engine, schema=self.schema,
                                         if_exists="replace", index=False)
        return len(df)

    def append(self, name: str, rows: Sequence[Dict]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        pd.DataFrame(rows).to_sql(name, self.engine, schema=self.schema,
                                  if_exists="append", index=False)
        return len(rows)

    def ids(self, name: str, column: str = "interaction_id") -> set:
        from sqlalchemy import text
        if not self.has(name):
            return set()
        sql = f"SELECT {self._qi(column)} FROM {self._q(name)}"
        with self.engine.connect() as conn:
            return {r[0] for r in conn.execute(text(sql))}

    # identifier quoting
    def _qi(self, identifier: str) -> str:
        """Quote one identifier using the dialect's own rules."""
        return self.engine.dialect.identifier_preparer.quote(identifier)

    def _q(self, name: str) -> str:
        """Quote a table name, schema-qualified when a schema was configured."""
        return f"{self._qi(self.schema)}.{self._qi(name)}" if self.schema \
            else self._qi(name)
