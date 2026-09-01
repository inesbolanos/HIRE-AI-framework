"""Configuration for the H.I.R.E. AI analytics pipeline.

Loads a YAML config plus the (optional) warehouse connection URL from the
environment and loads everything into frozen dataclasses.
This is the source for:
    * table names and the database they live in
    * column names
    * LLM settings: models, the warehouse SQL function, and thresholds used
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Dict, List

import yaml

from . import constants as const

try:  # optional: load a local .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a convenience, not required
    pass


@dataclass(frozen=True)
class Tables:
    """Pipeline stages: each is one table in the configured database. The unique id is
    interaction_id: each row is one interaction between a user (input) and an
    agent (output)."""
    source: str
    deterministic: str
    classified: str
    escalation: str
    audit: str
    review: str
    topics: str
    topic_map: str
    metrics: str
    conversation_metrics: str


@dataclass(frozen=True)
class Columns:
    """Raw source-schema columns (what the source CSV provides). These are fixed by
    the dataset schema, so they live here as defaults rather than in config.yaml.
    """
    interaction_id: str = "interaction_id"
    conversation_id: str = "conversation_id"
    turn: str = "turn"               
    date: str = "event_date"
    input_text: str = "user_input"
    output_text: str = "agent_output"
    user_signal: str = "user_control_id"
    agent_signal: str = "agent_action_id"


@dataclass(frozen=True)
class Deterministic:
    """Step 1 (deterministic rules): the derived category columns the rules write,
    and the label given to interactions NO rule matched (these free-text 'manual
    inputs' flow to the LLM layers, Steps 2-5). Loaded from the `deterministic:`
    section of config.yaml."""
    input_category: str
    output_category: str
    freeform_input_label: str
    freeform_output_label: str


@dataclass(frozen=True)
class Storage:
    """Where the pipeline's own tables live (its stage outputs, not your source data).

    Always a database. `url_env` names the environment variable holding a SQLAlchemy
    URL, so the connection string is never committed:

      * a **data warehouse** URL (Databricks, Snowflake, Postgres…) — and if the LLM
        layers run there too, data and model share one platform; or
      * ``sqlite:///hire.db`` — a real database in a local file, no server and no
        credentials, for trying the pipeline out.

    `default_url` is the fallback used when that variable is unset, so the sample
    data runs with zero setup.
    """
    url_env: str = "HIRE_STORE_URL"          # env var holding the SQLAlchemy URL
    default_url: str = "sqlite:///hire.db"   # used when url_env is unset
    schema: str = ""                         # optional schema/database for the tables


@dataclass(frozen=True)
class Models:
    """Which models run the LLM layers, and where they run.

    The LLM layers run inside your data warehouse via its own SQL function, so the
    workspace entitlement is the authentication. `classifier` / `judge` are model or
    endpoint names as your platform spells them, and `sql_template` is the
    platform's LLM function, e.g. ``ai_query('{model}', {input})``.

    `provider` exists so another backend can be added as an LLMClient subclass
    (see llm.py); "warehouse" is the one that ships.
    """
    classifier: str
    judge: str
    sql_template: str = ""                   # e.g. ai_query('{model}', {input})
    provider: str = "warehouse"
    sql_url_env: str = "HIRE_SQL_URL"        # env var holding the SQLAlchemy URL


@dataclass(frozen=True)
class RunOpts:
    batch_size: int
    max_chars: int
    confidence_threshold: float
    max_retries: int
    language_hint: str


@dataclass(frozen=True)
class Discovery:
    cluster_min_size: int
    hdbscan_min_samples: int
    umap_n_neighbors: int
    umap_seed: int
    refit_outlier_threshold: float
    model_dir: str


@dataclass(frozen=True)
class Rules:
    """The `rules:` block of taxonomy.yaml: the deterministic routing contract.

    Declared as a dataclass so an unknown key raises instead of being ignored. 
    A misspelled 'intent_resolving_actions' would otherwise zero out both IRR and
    PPR on a run that reported success. Its fields are flattened onto Taxonomy.
    """
    user_controls: Dict[str, str] = field(default_factory=dict)
    agent_actions: Dict[str, str] = field(default_factory=dict)
    intent_resolving_actions: Dict[str, List[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Metrics:
    """The `metrics:` block of taxonomy.yaml: Step 6 agent-metrics config.

    Same reason as Rules: the constructor is the allowlist, so the set of legal
    keys can never drift out of step with the fields the code actually reads.
    """
    red_line_categories: List[str] = field(default_factory=list)
    red_line_patterns: List[str] = field(default_factory=list)
    correction_categories: List[str] = field(default_factory=list)
    frustration_tones: List[str] = field(default_factory=list)
    escalation_categories: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Taxonomy:
    """The agent's vocabulary + deterministic contract, loaded from taxonomy.yaml.
    Single source of truth for category names — edit that file (not code) to adapt
    the framework to a different agent."""
    agent_description: str
    input_labels: Dict[str, str]     # user category -> description
    output_labels: Dict[str, str]    # agent category -> description
    tone_labels: Dict[str, str]      # tone -> description
    input_examples: List[Dict]       # few-shots: {text, category, reason}
    output_examples: List[Dict]
    user_controls: Dict[str, str]    # control id -> user category (deterministic)
    agent_actions: Dict[str, str]    # action id -> agent category (deterministic)
    intent_resolving_actions: Dict[str, set]  # user intent -> {resolving action categories}

    # Step 6 agent-metrics config (from the `metrics:` section of taxonomy.yaml)
    red_line_categories: List[str]   # agent categories that are a compliance red line
    red_line_patterns: List[str]     # regexes over agent text flagging a security breach
    correction_categories: List[str] # user categories meaning "corrected the agent"
    frustration_tones: List[str]     # tones signalling frustration (feed DIY)
    escalation_categories: List[str] # user categories meaning "gave up on the agent"


@dataclass(frozen=True)
class Config:
    tables: Tables
    deterministic: Deterministic
    models: Models
    run: RunOpts
    discovery: Discovery
    taxonomy: Taxonomy
    columns: Columns = field(default_factory=Columns)  # fixed source schema (code default)
    storage: Storage = field(default_factory=Storage)  # where the pipeline's tables live
    store_url: str = field(repr=False, default="")     # secret; from storage.url_env
    sql_url: str = field(repr=False, default="")       # secret; from models.sql_url_env

    # role helpers: one interaction, two classifiable roles (user / agent)
    def roles(self) -> List[Dict]:
        """The two roles of an interaction the LLM layers classify.
        """
        return [
            {"prefix": "input",
             "content_col": self.columns.input_text,
             "category_col": self.deterministic.input_category,
             "freeform_label": self.deterministic.freeform_input_label,
             "taxonomy_role": "user",
             "tone": True},
            {"prefix": "output",
             "content_col": self.columns.output_text,
             "category_col": self.deterministic.output_category,
             "freeform_label": self.deterministic.freeform_output_label,
             "taxonomy_role": "agent",
             "tone": False},
        ]
_CONFIG_KEYS = {"taxonomy_file", "storage", "tables", "deterministic",
                "models", "run", "discovery"}
_TAXONOMY_KEYS = {"agent_description", "input_labels", "output_labels", "tone_labels",
                  "input_examples", "output_examples", "rules", "metrics"}


def _read_yaml(path: str) -> Dict:
    """Read a YAML file, reporting a missing or malformed file as a ValueError.

    Both are ordinary user situations rather than bugs, and ValueError is what the
    CLI catches to print guidance instead of a stack trace.
    """
    if not os.path.isfile(path):
        raise ValueError(
            f"Config file not found: {path}\n"
            "Copy the shipped example to get started:\n"
            "  cp config.example.yaml config.yaml"
        )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{os.path.basename(path)} is not valid YAML:\n{e}") from e


def _reject_unknown(block: Dict, known: set, where: str) -> None:
    """Fail on a file-level key we don't understand, rather than ignoring it."""
    unknown = sorted(set(block or {}) - known)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown}. Known keys: {sorted(known)}.\n"
            "Unknown keys are rejected rather than ignored, so a typo or a stale "
            "edit cannot silently disable a rule or a metric."
        )


def _block(cls, raw_block, where: str):
    """Build a config dataclass from a YAML block, reporting key errors clearly."""
    data = raw_block or {}
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {unknown}. Known keys: {sorted(known)}.\n"
            "Unknown keys are rejected rather than ignored, so a typo or a stale "
            "edit cannot silently disable a rule or a metric."
        )
    try:
        return cls(**data)
    except TypeError as e:                        # a required key is missing
        raise ValueError(f"{where}: {e}") from e


def _load_taxonomy(path: str) -> Taxonomy:
    """Load the data-driven taxonomy (labels, tones, few-shots, deterministic maps)."""
    raw = _read_yaml(path)
    _reject_unknown(raw, _TAXONOMY_KEYS, "taxonomy.yaml")
    missing = [k for k in ("input_labels", "output_labels", "tone_labels") if k not in raw]
    if missing:
        raise ValueError(
            f"taxonomy.yaml is missing required section(s): {missing}. "
            "Every label set the prompts and metrics read comes from this file; "
            "see the shipped taxonomy.yaml for the expected shape."
        )
    rules = _block(Rules, raw.get("rules"), "taxonomy.yaml: rules")
    metrics = _block(Metrics, raw.get("metrics"), "taxonomy.yaml: metrics")
    tax = Taxonomy(
        agent_description=raw.get("agent_description", ""),
        input_labels=raw["input_labels"],
        output_labels=raw["output_labels"],
        tone_labels=raw["tone_labels"],
        input_examples=raw.get("input_examples", []) or [],
        output_examples=raw.get("output_examples", []) or [],
        user_controls=rules.user_controls,
        agent_actions=rules.agent_actions,
        intent_resolving_actions={k: set(v or [])
                                  for k, v in rules.intent_resolving_actions.items()},
        red_line_categories=metrics.red_line_categories,
        red_line_patterns=metrics.red_line_patterns,
        correction_categories=metrics.correction_categories,
        frustration_tones=metrics.frustration_tones,
        escalation_categories=metrics.escalation_categories,
    )
    _validate_taxonomy(tax)
    return tax


def _validate_taxonomy(t: Taxonomy) -> None:
    """Catch the drift the data-driven design is meant to prevent: resolving-action
    references that don't line up with the declared intents and actions."""
    intents = set(t.input_labels)
    actions = set(t.agent_actions.values())
    for intent, acts in t.intent_resolving_actions.items():
        if intent not in intents:
            raise ValueError(f"taxonomy: intent_resolving_actions has unknown intent '{intent}' "
                             f"(not a key in input_labels)")
        unknown = set(acts) - actions
        if unknown:
            raise ValueError(f"taxonomy: intent_resolving_actions['{intent}'] references unknown "
                             f"action(s) {sorted(unknown)} (not values in rules.agent_actions)")

    # Values the pipeline CODE special-cases (constants.py) must exist in the data,
    # or steps would silently mis-handle them.
    for labels, name in ((t.input_labels, "input_labels"), (t.output_labels, "output_labels")):
        if const.OTHER not in labels:
            raise ValueError(f"taxonomy: {name} must define an '{const.OTHER}' category "
                             f"(the pipeline special-cases it as the residual bucket)")
    user_categories = set(t.input_labels) | set(t.user_controls.values())
    if const.END_CONVERSATION not in user_categories:
        raise ValueError(f"taxonomy: '{const.END_CONVERSATION}' must appear as an input label "
                         f"or a user_controls value (Step 1 resolution special-cases it)")

    # Step 6 metrics config must reference real categories/tones.
    for names, universe, where in (
        (t.red_line_categories, set(t.output_labels), "metrics.red_line_categories / output_labels"),
        (t.correction_categories, set(t.input_labels), "metrics.correction_categories / input_labels"),
        (t.escalation_categories, set(t.input_labels), "metrics.escalation_categories / input_labels"),
        (t.frustration_tones, set(t.tone_labels), "metrics.frustration_tones / tone_labels"),
    ):
        unknown = set(names) - universe
        if unknown:
            raise ValueError(f"taxonomy: {sorted(unknown)} in {where} are not defined")


def load_config(path: str) -> Config:
    """Read config.yaml + taxonomy.yaml (+ the connection URLs from the environment).

    Two URLs, both read from environment variables named in the YAML so that no
    connection string is ever committed:

      * ``storage.url_env`` — where the pipeline's tables are written. Falls back to
        ``storage.default_url`` (a local SQLite file), so Steps 1 and 6 still run
        with no server and no credentials.
      * ``models.sql_url_env`` — the warehouse that runs the LLM layers (Steps 2-5).

    Point both at the same warehouse and the data and the model share one platform.
    The taxonomy file path comes from ``taxonomy_file`` (default ``taxonomy.yaml``),
    resolved relative to config.yaml.
    """
    raw = _read_yaml(path)

    name = os.path.basename(path)
    # A misspelled top-level block would otherwise fall back to its default in
    # silence — e.g. 'storgae:' leaves you on local SQLite while you believe you
    # are pointed at a warehouse.
    _reject_unknown(raw, _CONFIG_KEYS, name)

    tax_file = raw.get("taxonomy_file", "taxonomy.yaml")
    tax_path = tax_file if os.path.isabs(tax_file) else \
        os.path.join(os.path.dirname(os.path.abspath(path)), tax_file)

    models = _block(Models, raw.get("models"), f"{name}: models")
    storage = _block(Storage, raw.get("storage"), f"{name}: storage")

    return Config(
        tables=_block(Tables, raw.get("tables"), f"{name}: tables"),
        deterministic=_block(Deterministic, raw.get("deterministic"), f"{name}: deterministic"),
        models=models,
        run=_block(RunOpts, raw.get("run"), f"{name}: run"),
        discovery=_block(Discovery, raw.get("discovery"), f"{name}: discovery"),
        taxonomy=_load_taxonomy(tax_path),
        storage=storage,
        store_url=os.environ.get(storage.url_env, "") or storage.default_url,
        sql_url=os.environ.get(models.sql_url_env, ""),
    )