"""Pluggable LLM client: the LLM layers run inside your data warehouse.

The shipped client is `WarehouseClient`: it runs the model through the warehouse's
own SQL function (Databricks `ai_query`, Snowflake `CORTEX.COMPLETE`, …). That is
a deliberate choice, not a limitation:

  * **No personal API key.** The warehouse holds the model entitlement, so your
    existing workspace credentials are the authentication. 
  * **Data stays put.** Conversation transcripts never leave the platform they
    already live in, which is usually the only compliant option for real data.
  * **Set-based inference.** A whole batch of messages is one query rather than
    hundreds of round trips.

The rest of the pipeline depends only on the LLMClient interface below, so a
different backend (a hosted API, a local model) is a small subclass: implement
`classify()` and optionally `embed()`, then inject it:

    pipeline.run(cfg, store, llm=MyClient())

The classifier enforces STRICT JSON via a response schema. `classify()` handles a
single text; `classify_batch()` handles many and is what the pipeline calls, so
providers that support set-based inference can push a whole batch down at once.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

from . import constants as const

logger = logging.getLogger("hire.llm")


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Interface. Subclass for a specific provider."""

    def classify(self, prompt: str, text_value: str, schema: Dict[str, Any],
                 model: Optional[str] = None) -> Dict[str, Any]:
        """Classify one text with one prompt. `model` names the model/endpoint so
        one client can serve both the cheap first pass and the stronger judge;
        None means the implementation's own default."""
        raise NotImplementedError

    def classify_batch(self, prompt: str, texts: Sequence[str], schema: Dict[str, Any],
                       model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Classify many texts with one prompt; returns one dict per text, in order.

        The default loops `classify()`, so a provider only needs `classify()` to
        work. Providers that can do set-based inference override this: a warehouse
        classifies a whole batch in a single SQL statement instead of N round
        trips, which is the difference between one query and several hundred.
        """
        return [self.classify(prompt, t, schema, model=model) for t in texts]

    def complete(self, prompt: str, model: Optional[str] = None) -> str:
        """Free-form text completion (used by Step 5 cluster naming / consolidation)."""
        raise NotImplementedError

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Turns text into numbers for clustering / similarity search (Step 5)."""
        raise NotImplementedError


def build_classification_input(prompt: str, text_value: str) -> str:
    """The exact text sent to a model for one classification.

    Shared by every client so the wording is identical no matter which provider runs it
    """
    return (
        f"{prompt}\n\nTEXT TO CLASSIFY:\n\"\"\"\n{text_value}\n\"\"\"\n\n"
        "Respond with STRICT JSON only, no prose, no code fences."
    )


def build_batch_sql(sql_template: str, model: str, n_rows: int) -> str:
    """Build one set-based classification statement for `n_rows` prompts.

    Kept as a pure function (no engine, no driver) so it can be read and tested
    without a warehouse connection.

    `sql_template` is the platform's LLM function with two placeholders:
      {model}: the model/endpoint name        {input}: the prompt column

        Databricks   ai_query('{model}', {input})
        Snowflake    SNOWFLAKE.CORTEX.COMPLETE('{model}', {input})

    The prompt rows are supplied as bound parameters (:p0, :p1, …) via a
    UNION ALL row constructor: the most portable one across SQL dialects, and
    parameterized so prompt text containing quotes or braces can never break or
    inject into the statement.
    """
    if n_rows < 1:
        raise ValueError("n_rows must be >= 1")
    if "{input}" not in sql_template:
        raise ValueError(
            f"sql_template must contain the {{input}} placeholder; got {sql_template!r}"
        )
    rows = " UNION ALL ".join(
        (f"SELECT {i} AS idx, :p{i} AS txt" if i == 0 else f"SELECT {i}, :p{i}")
        for i in range(n_rows)
    )
    call = sql_template.format(model=model, input="txt")
    return f"SELECT idx, {call} AS response FROM ({rows}) t ORDER BY idx"


class WarehouseClient(LLMClient):
    """Run the LLM layers **inside your data warehouse**, via its own SQL function.
    Your existing workspace credentials are the authentication. 

    Vendor differences collapse into a single configurable expression
    (`models.sql_template`): see build_batch_sql for the per-platform forms.
    Needs SQLAlchemy plus your platform's driver: `pip install -e '.[sql]'`.
    """

    def __init__(self, url: str, classifier_model: str, judge_model: str,
                 sql_template: str, max_retries: int = 3, batch_size: int = 100,
                 embed_fn=None, engine=None):
        self.sql_template = sql_template
        self.classifier_model = classifier_model
        self.judge_model = judge_model
        self.max_retries = max_retries
        self.batch_size = max(1, batch_size)
        self._embed_fn = embed_fn
        if engine is not None:            # injected (tests, or your own engine)
            self._engine = engine
        else:
            try:
                from sqlalchemy import create_engine  # lazy: optional dependency
            except ImportError as e:  # pragma: no cover
                raise LLMError(
                    "The warehouse provider needs SQLAlchemy plus your platform's "
                    "dialect: pip install -e '.[sql]' (then e.g. databricks-sqlalchemy "
                    "or snowflake-sqlalchemy)."
                ) from e
            if not url:
                raise LLMError(
                    "No warehouse connection URL. Set the environment variable named "
                    "by models.sql_url_env (default HIRE_SQL_URL) to a SQLAlchemy URL."
                )
            self._engine = create_engine(url)

    # classification
    def classify(self, prompt: str, text_value: str, schema: Dict[str, Any],
                 model: Optional[str] = None) -> Dict[str, Any]:
        return self.classify_batch(prompt, [text_value], schema, model=model)[0]

    def classify_batch(self, prompt: str, texts: Sequence[str], schema: Dict[str, Any],
                       model: Optional[str] = None) -> List[Dict[str, Any]]:
        """Classify every text in one statement per chunk (the whole point)."""
        model = model or self.classifier_model
        out: List[Dict[str, Any]] = []
        texts = list(texts)
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start:start + self.batch_size]
            prompts = [build_classification_input(prompt, t) for t in chunk]
            responses = self._run(model, prompts)
            if len(responses) != len(chunk):
                raise LLMError(
                    f"Warehouse returned {len(responses)} rows for {len(chunk)} prompts; "
                    "check that sql_template returns exactly one value per row."
                )
            out.extend(parse_json(r) for r in responses)
        return out

    def complete(self, prompt: str, model: Optional[str] = None) -> str:
        return self._run(model or self.judge_model, [prompt])[0]

    # embeddings
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if self._embed_fn is None:
            raise LLMError(
                "The warehouse client does not generate embeddings (vector return "
                "types differ too much between platforms to be portable). For Step 5, "
                "pass embed_fn=default_embed_fn() to run embeddings locally with no "
                "API key, or compute them in your warehouse and load the vectors."
            )
        return self._embed_fn(list(texts))

    # transport
    def _run(self, model: str, prompts: List[str]) -> List[str]:
        sql = build_batch_sql(self.sql_template, model, len(prompts))
        params = {f"p{i}": p for i, p in enumerate(prompts)}
        return self._execute(sql, params)

    def _execute(self, sql: str, params: Dict[str, str]) -> List[str]:
        """Run one statement, with the same backoff/retry policy as the other clients."""
        from sqlalchemy import text as sa_text  # lazy: optional dependency

        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with self._engine.connect() as conn:
                    rows = conn.execute(sa_text(sql), params).fetchall()
                return [_coerce_text(r[1]) for r in rows]   # (idx, response)
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:      # no pointless sleep after the last attempt
                    wait = 2 ** (attempt - 1)
                    logger.warning("Warehouse query failed (attempt %d/%d): %s; retrying in %ds",
                                   attempt, self.max_retries, e, wait)
                    time.sleep(wait)
        raise LLMError(f"Warehouse query failed after {self.max_retries} retries: {last_err}")


def _coerce_text(value: Any) -> str:
    """Warehouse LLM functions return a string on some platforms and a
    struct/variant on others; normalize to the raw text for parse_json."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def parse_json(raw: str) -> Dict[str, Any]:
    """Parse an LLM response into a dict, tolerating stray code fences / prose."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):] if "{" in s else s
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1:
        s = s[start:end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        logger.error("Could not parse LLM JSON: %s", raw[:200])
        # Safe fallback so one bad row can't kill the batch.
        return {"reason": "unparseable model output", "category": const.OTHER,
                "confidence": 0.0, "tone": const.OTHER}


def default_embed_fn(model_name: str = "all-MiniLM-L6-v2"):
    """Return a local sentence-transformers embed function (optional dependency).

    Kept out of the hot import path so the package installs without torch. Call
    this only if you want zero-API-cost embeddings for Step 5.
    """
    def _fn(texts: List[str]) -> List[List[float]]:
        from sentence_transformers import SentenceTransformer  # lazy
        model = SentenceTransformer(model_name)
        return model.encode(texts, show_progress_bar=False).tolist()

    return _fn
