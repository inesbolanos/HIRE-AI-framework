# Case Study: Fraud / Banking Support Agent (Worked Example)

*A conversational agent that triages fraud reports: blocking cards, filing disputes, and securing accounts, before a human ever picks up the case.*

**Note:** This is a **fully synthetic worked example**: the "organization" is fictional and every number below is produced by running this repository's analytics pipeline on the bundled sample dataset ([datasets/fraud-agent](../datasets/fraud-agent/DATASET.md)). No real customers, transcripts, or metrics are involved. Use it as a template for what a completed, data-backed case study looks like — and reproduce every figure yourself with the [Quick Start](../README.md#quick-start).

| | |
|---|---|
| **Organization** | Fictional retail bank (synthetic example) |
| **Industry** | Banking / financial services |
| **Challenge** | Fraud reports are urgent and high-volume, but most arrive as free text a rules-based flow can't triage |
| **Solution** | A support agent with structured controls for known intents plus LLM reasoning for free-text triage, with human-in-the-loop on account actions |
| **Impact** | 85% of resolvable conversations reached a resolving action — but only 48.9% on the first exchange (deterministic measurement) |
| **Timeline** | 6 weeks of simulated traffic (Jan–Feb 2024, 364 conversations / 603 interactions) |
| **Team** | Fraud operations + risk platform engineering (fictional) |
| **Status** | 🟡 Pilot (synthetic) |
| **H.I.R.E. Score** | 42/77 — 🟡 TRAIN (strong job, execution risk is the gap) |

## The Problem

**Scenario:** A customer spots a charge they didn't make. It's 9pm. The fraud hotline queue is 40 minutes deep, and every minute the card stays active is another potential charge. They open the bank's chat and type: *"Someone used my card without permission."*

**Challenge:**
- Fraud is time-critical: the value of blocking a card decays by the minute.
- Intents are finite and well-known (unauthorized charge, phishing, lost card, account takeover, dispute, refund status) — but customers phrase them in unbounded ways.
- Menu-only flows miss the customers who type instead of tap; hotline-only support doesn't scale to spikes.
- Agents that over-promise ("100% you'll get your money back") create compliance exposure.

**Root Cause:** The set of things the bank can *do* about fraud is small and structured; the set of ways customers *ask* for them is not.

## The Solution: Fraud Support Agent

### What We Built

A chat agent whose front door is structured: a main menu, quick-reply buttons, and a dispute form that map 1:1 to known intents with zero model involvement, backed by LLM reasoning for everything typed as free text. Account actions (block card, file dispute, secure account, initiate refund) are structured `system_action`s, never free-form generation.

**Key Capabilities:**
- **Structured intake:** menu/buttons/forms route known intents deterministically (no drift, no hallucination).
- **Free-text triage:** typed reports are classified onto the same intent taxonomy by the LLM layers.
- **Account actions:** block card, file dispute, secure account, initiate refund — as auditable structured actions.
- **Escalation:** "talk to a human" is a first-class button and a recognized free-text intent.

## H.I.R.E. Framework Evaluation

### H - Human & Habits

| Evaluation | Description | Scoring |
|----------|------------------|---------------------|
| **Trust assessment** | Customers already trust chat for banking tasks; fraud ops team is new to AI triage | 🟡 2 |
| **Cultural fit** | Fraud ops already works from a fixed intent playbook: the taxonomy mirrors it | 🟢 3 |
| **User control** | Every account action is a visible, structured step; customers can escalate to a human at any turn | 🟢 3 |
| **Change management plan** | Piloted alongside (not replacing) the hotline; feedback loop via the analytics pipeline | 🟡 2 |
| **Data quality** | Every interaction logs the control tapped and action taken | 🟢 3 |
| **System integration** | Actions call the same case-management APIs human agents use | 🟢 3 |
| **Interaction with user** | Reactive: waits for the customer to open chat | 🔴 1 |

**Score: 17/21** (strong data and control story; reactive by design, and change management is pilot-stage)

---

### I - Impact & Intent

**Job Description:** Front-line Fraud Triage Specialist

*"Hired to take the first pass on every inbound fraud contact: identify the intent, take the safe structured action (block, dispute, secure, refund) or gather what a human needs to act, and never promise an outcome. Success = resolving routine cases on the first exchange and routing the rest to humans with full context."*

**Boundaries:**
- Cannot guarantee refund outcomes (over-promising is a tracked red line: `overpromise_guarantee`)
- Cannot take an account action outside the structured action set
- Cannot handle non-fraud banking requests (out of scope → `other` → discovery)
- Cannot override a customer's request for a human

**Performance Review (Target KPIs):**
- Instant Resolution Rate (IRR): >60%
- Fine, Do It Yourself Rate (DIY): <15%
- Red Line Rate (RLR): 0%
- User Correction Rate (UCR): <15%
- Ping Pong Rate (PPR): ≤1.2 turns

*(the `Good` bands from the [AI Agent Metrics Guide](../framework/agent-metrics/ai-agent-metrics.md) — a real project may tighten them, but shouldn't loosen them past the guide's `Critical` column)*
- Deterministic coverage: stable or rising trend

**Problem Frequency & ROI:**

| Evaluation | Description | Scoring |
|----------|------------------|---------------------|
| **Problem frequency** | Fraud contacts arrive daily, with spikes after breach events | 🟢 5 |
| **Time savings** | Routine block/dispute cases skip the hotline queue entirely | 🟡 3 |
| **ROI** | Deflects the highest-volume, lowest-complexity contacts | 🟢 5 |
| **Strategic value** | Table stakes for digital banking rather than differentiation | 🟡 2 |

**Score: 15/17** (high-frequency, well-bounded job with a clear description)

---

### R - Rules vs. Responses vs. Reasoning

**Task Classification:** This problem needs **reasoning on top of rules**, because the actions are structured but the requests are free text.

| Approach | What It Would Do | Why It's Not Enough (or Why It Works) |
|----------|------------------|---------------------|
| **Rule** | Menu + buttons + dispute form | Works perfectly — for the 38.6% of user messages that arrive through a control. Regex over the typed 61.4% is guessing, not categorizing. |
| **Chatbot** | FAQ-style answers about fraud policy | Can explain, but can't run the multi-step triage (identify intent → gather details → take the action). |
| **Reasoning Agent** | Classify free text onto the intent taxonomy, gather missing details, choose the structured action | Right level: ambiguity lives only in the language; the action space stays deterministic. |

**Score: Reasoning-level task** (hybrid: rules first, reasoning only for the residual)

---

### E - Exposure & Execution

| Risk, Guardrails & Execution Boundaries | Description | Scoring |
|----------|------------------|---------------------|
| **Worst-case scenario** | The agent blocks the wrong card or promises a refund it can't deliver: costly and trust-damaging, but recoverable and bounded by the structured action set | 🟡 -10 |
| **Human-in-the-loop** | Escalation is one tap away; ambiguous LLM classifications route to a human review queue | 🟢 5 |
| **Deterministic security** | Identity/authorization checks are platform rules, never delegated to the model | 🟢 5 |
| **Rollback capability** | Card unblock and dispute withdrawal are existing bank operations | 🟢 5 |
| **Audit trails** | Every interaction logs the control, the action, and the classification (the pipeline's source table *is* the audit log) | 🟢 5 |
| **Tenant isolation** | Conversations are scoped to the authenticated customer | 🟢 5 |
| **Read-only access** | Write access: the agent takes account actions (mitigated by the fixed action set) | 🔴 -10 |
| **Failure mode** | Fallback is the same hotline that existed before the agent | 🟢 5 |
| | | **= 10** |

**Score: 10/39.** Every guardrail that can be earned is earned; the score is low because this agent *executes* on a moderate-risk surface, and no amount of tooling makes that free. The worst-case row is deliberately in the table rather than above it: it is mandatory and always negative, so keeping it in the visible sum is what stops it being quietly dropped (see the note below).

---

### Total Score: 42/77 🟡 TRAIN

**Verdict:** Train, not hire. The gap is entirely in **E**. H (17/21) and I (15/17) say this is a high-frequency, well-bounded problem where language ambiguity is the only probabilistic part. E (10/39) says the agent takes irreversible-ish actions on a moderate-risk surface, and the guardrails are already maxed out: there is no guardrail left to add.

That is a genuinely useful result: it says *narrow the blast radius, don't add more controls*. The concrete path to HIRE is to move the highest-risk actions behind explicit human approval (turning write access into suggest-only for those), which is worth +20 on its own and would put this comfortably over 50.

## Results

Every number in this section is what the pipeline reports on the synthetic dataset. Reproduce it with the no-API-key Quick Start (`ingest`, `metrics`, `agent-metrics`).

### Quantitative Impact (Step 1 + Step 6, deterministic — no LLM)

| Metric | Value | Reading |
|--------|-------|---------|
| **Deterministic coverage (user side)** | 38.6% (233/603) | The structured contract catches about 4 in 10 inputs; the 61.4% residual is the LLM layers' workload. Track the *trend*, not the snapshot. |
| **Deterministic coverage (agent side)** | 8.0% (48/603) | Most agent replies are free text, expected for a conversational agent. |
| **Instant Resolution Rate (IRR)** | 48.9% (23/47) | Of the 47 conversations with a resolvable intent, 23 got the resolving action on turn 1. |
| **Ping Pong Rate (PPR)** | 1.53 turns | Resolutions land on turn 1, 2 or 3 (23 / 13 / 4). When it isn't instant, it's usually one clarifying question. |
| **Fine, Do It Yourself Rate (DIY)** | 52.5% | High, but deterministic-only measurement over-counts it (see note). |
| **Red Line Rate (RLR)** | 0.3% (2/603) | Two replies leaked a credential in plaintext, caught by `red_line_patterns` regex, **no model involved**. Three over-promising replies also exist but need Step 2 to surface. |
| **Resolution (conversation level)** | 40 resolved / 7 unresolved / 0 abandoned / 317 undetermined | 317 conversations opened with free text, so resolution can't be judged until the LLM layers classify the intent. |

**The IRR/PPR pair is the finding.** 40 of 47 resolvable conversations (85%) did reach a
resolving action: the agent is not failing to resolve. But only 23 got there on the
first exchange, and PPR of 1.53 says the rest usually needed a single clarifying
question. Read alone, IRR looks like a problem; read next to PPR, it says the agent
asks one good question rather than guessing. That is the pairing the
[metrics guide](../framework/agent-metrics/ai-agent-metrics.md) argues for, and it is
why neither number should be quoted on its own.

*Note: this is the honest picture of what rules alone can see. DIY and UCR are still
under-stated, and RLR only shows its regex half, until Steps 2–5 classify the
free-text residual, which is precisely the framework's argument for evaluating the
evaluator before trusting any downstream number (calibrate with `evaluate` against the
labeled gold set).*

### What the LLM layers add (Steps 2–5)

Running the full pipeline moves exactly the metrics that depend on classification, and
leaves the deterministic ones untouched, a useful check that the two halves are
genuinely separate:

| Metric | Rules only | With Steps 2–5 | Why it moves |
|---|---|---|---|
| **UCR** | 0.0% | 6.0% | `correction` is an LLM label — no button says "you got that wrong" |
| **RLR** | 0.3% | 0.8% | adds the 3 `overpromise_guarantee` replies to the 2 regex-caught leaks |
| **IRR / PPR / coverage** | — | unchanged | computed from structured signals only |

A UCR of `0.0%` before Step 2 is not a clean bill of health; it means the metric was
not measured. That distinction is the single easiest way to misread this table.

### Qualitative Feedback (what the dataset encodes)

**What's working:**
- Structured openers usually resolve on the first turn: the deterministic path is the fast path.
- When the agent does need more information, it typically needs it once: PPR of 1.53 over 40 resolved conversations.
- "Known but missed" typed messages (*"Someone used my card without permission."*) map cleanly onto existing intents: routing gaps, not capability gaps.

**When it doesn't work:**
- Out-of-contract asks (*"Is my money safe?"*, *"How long does an investigation take?"*) fall to `other`: step 5 discovery clusters them into candidate new capabilities.
- Two replies handed a credential back to the user in plaintext (*"your temporary PIN is 4821"*): caught by regex, so this is the one red line visible without any model.
- Three over-promising replies (*"100% you'll get your money back."*): the tracked compliance red line, visible only once Step 2 classifies the agent side.
- Conversations that trail off with the user repeating themselves (*"This is the third time I've told you…"*) and never reaching an action: the DIY signal.

## When we would FIRE this agent

The metrics guide's **Critical** bands, applied to this agent. Each is qualified by
*measured with classified intents* because the deterministic-only figures above are
computed over a small structured-only slice — they are a baseline, not a trigger.

- **RLR** above 0% once the LLM layers are calibrated: any violation is a compliance event, and this is the one threshold not to relax
- **DIY** above 15% once measured with classified intents: customers are routing around the agent
- **IRR** below 40% once measured with classified intents, with PPR rising alongside it: triage is adding a step instead of removing one. (The deterministic-only IRR above sits at 48.9%, but over just 47 structured conversations — too small a denominator, and too narrow a slice, to trigger this rule.)
- **PPR** above 2.0 turns while IRR falls: the agent is circling rather than clarifying
- **Deterministic coverage** trends steadily down with no matching backlog of promoted rules: the contract has stopped tracking demand

## Key Takeaways

### For Product Managers
- **The contract is the product:** the structured controls define what the agent can do; the coverage *trend* tells you when demand has drifted past it.
- **"Known but missed" is your cheapest roadmap:** typed messages that map to existing intents are routing fixes, not new features.

### For Engineering Teams
- **Keep the action space deterministic:** let the model interpret language, never invent actions — worst cases stay bounded.
- **Log the routing signal, not just the text:** `user_control_id` / `agent_action_id` columns are what make Step 1 (and the audit trail) possible.

### For Data & Analytics Teams
- **Measure deterministically first:** Step 1 + Step 6 run with no API key and no drift — that baseline is what makes the LLM layers' contribution measurable.
- **Evaluate the evaluator:** none of the LLM-derived numbers are trustworthy until scored against the gold set (`evaluate` + threshold calibration).

**Key Takeaway:** When the actions are finite and the language is not, split the system the way this pipeline splits measurement — rules for what's structured, reasoning for the residual, and a gold set before you believe either.

## Contact

**Technical reference:** [datasets/fraud-agent/DATASET.md](../datasets/fraud-agent/DATASET.md) · [README Quick Start](../README.md#quick-start)

**First published:** 2026/08/29

**Last updated:** 2026/08/31