# The H.I.R.E. AI Framework: Analytics-Driven AI Agent Evaluation

> **When to Hire, Train or Fire Your AI Agent.**
> A strategic playbook and analytics toolkit for evaluating, building, and measuring the real business impact of AI Agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)

## About This Repository

This repository is an **open-source implementation** of the H.I.R.E. Framework, presented at [Data & AI Tech Summit 2026](https://dataiwarsaw.tech/) and [AGNTCon + MCPCon Japan 2026](https://events.linuxfoundation.org/agntcon-mcpcon-japan/). It provides product teams, data analysts, and engineering leaders with structured tools to:

- **Evaluate** whether an AI agent is the right solution for a business problem
- **Measure** AI agent performance beyond traditional metrics
- **Scale** qualitative conversational data into actionable insights
- **Prevent** *"agent washing"* and hype-driven development

**This is a work in progress.** The goal is to build this collaboratively with the community. Contributions, feedback, and real-world case studies are highly encouraged.

## The H.I.R.E. Framework

It helps you decide when to **Hire**, **Train**, or **Fire** your AI agents by evaluating four critical dimensions:

### **H** - Human & Habits
- Is your team culturally ready to trust AI in this workflow?
- Are your data systems and tools prepared to support an agent?
- Can users edit the agent's memory and correct mistakes?

### **I** - Impact & Intent
- If this agent was a human, what job are we hiring them for?
- Does the problem frequency justify the engineering investment?
- Can we write a clear job description with measurable KPIs?

### **R** - Rules vs. Responses vs. Reasoning
- Is this task predictable? → Use **automation** (rules)
- Is this task informational? → Use a **chatbot** (responses)
- Is this task ambiguous and multi-step? → Use an **AI agent** (reasoning)

### **E** - Exposure & Execution
- If this agent makes the worst possible mistake, can the business survive?
- Are there human-in-the-loop guardrails in place?
- Is security handled deterministically, not probabilistically?

## How to Use This Toolkit
This repository contains practical templates and code snippets for the AI product development.

* **`/framework`:** practical implementation of the HIRE framework, with docs to guide you on the decision.
    * **`/agent-metrics`:** guidelines on how to calculate User Correction Rate (UCR), Ping Pong Rate (PPR), Do It Yourself Rate (DIY), Instant Resolution Rate (IRR) and Red Line Rate (RLR).
* **`/src/hire_pipeline`:** the analytics pipeline: deterministic telemetry → LLM classification → escalation → 'other' audit → topic discovery → agent metrics. Its tables are database tables: your warehouse, or a local SQLite file with zero setup.
* **`/taxonomy.yaml`:** the agent's contract (categories, tones, few-shots, routing rules). Edit this one file to adapt the whole pipeline to your own agent: no code changes needed.
* **`/datasets/fraud-agent`:** a synthetic, publishable sample dataset (fraud / banking support agent) with a reproducible generator and a labeled gold set.
* **[`/case-studies`](case-studies):** includes a template to share real-world case studies written by the community. Check how to [contribute](CONTRIBUTING.md) with yours.
* **`/tests`:** the pytest suite covering the pipeline's deterministic layer, prompts, evaluation, and metrics.

## Quick Start

1. **Evaluate your agent idea:** start with the H.I.R.E. checklist to determine if an AI agent is the right solution.
2. **Choose your metrics**: review the AI Agent Metrics Guide and select the KPIs that align with your business goals.

### Prerequisites
- Python 3.9+
- Access to conversational data (chat transcripts, logs) or use the bundled synthetic sample dataset
- A database for the pipeline's tables: your data warehouse, or the default local SQLite file (no server, no credentials)
- (Optional) A data warehouse with an LLM function (Databricks, Snowflake, …) for the Step 2–5 classification/discovery layers (see [Running it in your data warehouse](#running-it-in-your-data-warehouse)). Steps 1 and 6 run with no credentials at all.

### Run the pipeline on the sample data
```bash
pip install -e '.[discovery,dev]'
cp config.example.yaml config.yaml

# 1) generate the synthetic sample dataset
python datasets/fraud-agent/generate_sample_data.py

# 2) ingest + deterministic Step 1
hire ingest --config config.yaml

# 3) print the per-day deterministic-coverage trend
hire metrics --config config.yaml

# 4) the five headline agent metrics (UCR, PPR, DIY, IRR, RLR)
hire agent-metrics --config config.yaml

# 5) full pipeline incl. LLM Steps 2–5 (runs the model in your warehouse)
hire run --config config.yaml

# 6) score the LLM layers against the labeled gold set (after step 5)
hire evaluate --config config.yaml
```
Steps 2–5 need a warehouse; everything else runs with no credentials at all. Tables are created in the database from `storage.url_env`, defaulting to a local `hire.db` SQLite file.

Run the test suite with `pytest` (no credentials, database or network needed).

### Running it in your data warehouse

Most people this framework is written for (product analysts, PMs, data teams) **cannot get an LLM API key**, because their organization issues keys only to developer accounts. But they do have a warehouse seat, and every major warehouse now exposes an LLM as a SQL function. Use that instead: the workspace entitlement is the authentication.

The pipeline ships no platform default: you pick yours in `config.yaml`:

| Platform | `sql_template` | `classifier` / `judge` examples |
|---|---|---|
| **Databricks** | `ai_query('{model}', {input})` | `databricks-meta-llama-3-3-70b-instruct` / `databricks-claude-sonnet-4` |
| **Snowflake** | `SNOWFLAKE.CORTEX.COMPLETE('{model}', {input})` | `llama3.1-8b` / `claude-3-5-sonnet` |
| **Anything else** | any scalar function `FN(model, prompt)` returning text | whatever your platform calls them |

```yaml
models:
  sql_template: "ai_query('{model}', {input})"   # your platform's LLM function
  sql_url_env:  HIRE_SQL_URL                     # env var holding the SQLAlchemy URL
  classifier:   databricks-meta-llama-3-3-70b-instruct   # cheap first pass
  judge:        databricks-claude-sonnet-4                # escalation, audit, naming
```

Any warehouse works the same way if its LLM is a **scalar** SQL function — `FN(model, prompt)` returning text. Put that call in `sql_template`, with `{model}` and `{input}` as the placeholders. Verify your platform's current signature; these have been moving targets. Install your platform's **SQLAlchemy dialect** (e.g. `databricks-sqlalchemy`, `snowflake-sqlalchemy`) — the dialect, not just the raw DBAPI driver, or SQLAlchemy can't load the `databricks://` URL scheme.

*BigQuery's `ML.GENERATE_TEXT` is table-valued rather than scalar, so it needs a small `LLMClient` subclass instead of a config change. Warehouses with no LLM function (Postgres, MySQL, DuckDB) can still run Steps 1 and 6 — coverage, resolution and all five agent metrics.*

Prompts are passed as bound parameters, never string-interpolated, so quotes and braces in your few-shot examples can't break or inject into the statement.

Three reasons this is usually the best option:

1. **No personal API key, and no developer role needed to get one**: the entitlement belongs to the workspace.
2. **Conversation data never leaves the platform it already lives in.** For real transcripts this is often the only compliant choice.
3. **Inference is set-based.** A batch of messages becomes one query instead of hundreds of round trips, so it is also the fastest option.

Not covered: Step 5 embeddings. Vector return types differ too much between platforms to abstract honestly — pass `embed_fn=default_embed_fn()` to compute them locally (no key), or generate them in your warehouse and load the vectors.

### Where the pipeline's tables live

Every pipeline stage is a **real database table**: these are analytical tables you'll want to query, join and trend over time. The connection comes from an environment variable, so it's never committed:

```yaml
storage:
  url_env:     HIRE_STORE_URL      # env var holding the SQLAlchemy URL
  default_url: sqlite:///hire.db   # fallback when that variable is unset
  schema:      analytics           # optional: where to create the tables
```

Point `HIRE_STORE_URL` at your **data warehouse** — ideally the same one running the models — and the data and the model share a platform, so nothing has to leave it. Set nothing and you get a local **SQLite file**: still a real database, but no server and no credentials, which is enough to run the sample data end to end. A trial run and a production run differ only by connection string.

One thing to know before pointing it at a warehouse: **`write()` replaces a table wholesale** (drop and recreate). That's what a full-refresh stage means here, but on a governed warehouse it can discard grants or table properties — so point `schema` at a working schema you own, not a curated one.

Any database with a [SQLAlchemy](https://www.sqlalchemy.org/) driver works — see [`src/hire_pipeline/store.py`](src/hire_pipeline/store.py).

## Key Metrics for AI Agents
The shift from deterministic to probabilistic software requires a shift in analytics as well. We need to stop measuring clicks and start measuring friction removed. This framework introduces five metrics:

**User Correction Rate (UCR)** · **Ping Pong Rate (PPR)** · **Fine, Do It Yourself Rate (DIY)** · **Instant Resolution Rate (IRR)** · **Red Line Rate (RLR)**

Definitions, formulas, thresholds and what counts (and doesn't) for each: **[AI Agent Metrics Guide](framework/agent-metrics/ai-agent-metrics.md)**

## Contributing
This framework is **community-driven**. How can you help?
- Add real-world case studies from your company
- Improve metric definitions and tracking techniques
- Build integrations with analytics platforms
- Translate this framework into other languages
- Challenge assumptions and suggest better approaches

See more in [CONTRIBUTING.md](CONTRIBUTING.md)

## Case Study: SRE Agent
The framework was developed while building an **SRE (Site Reliability Engineering) Agent** for incident management. Key learnings:

- **Problem**: engineers spent 3+ hours manually connecting outdated runbooks to current system logs during critical outages
- **Solution**: an AI agent that reads alerts, analyzes logs, adapts old runbooks, and drafts fix commands
- **Result**: faster incident resolution with human-in-the-loop (HITL) approval (metrics to be shared, pending on company approval)

## When NOT to Build an AI Agent

This framework will help you **fire** agents that shouldn't exist:

- The problem occurs less than 10 times per year (low ROI)
- A simple automation rule can solve it (don't take the high-speed train, just walk).
- The cost of a mistake is catastrophic (e.g., life-or-death scenarios)
- Your team isn't ready to trust AI in this workflow (cultural resistance)
- You can't build deterministic safety guardrails (security risk)

**Having the courage to fire an agent is what makes great product strategy.**

## License
This project is licensed under the MIT License: see the [LICENSE](LICENSE) file for details. Feel free to use these templates in your own company's workflows.

Created by Inês Bolaños, Senior Product Analyst at PagerDuty [say hi! on LinkedIn](https://www.linkedin.com/in/inesbolanos/). Based on real-world experience evaluating AI Agents.