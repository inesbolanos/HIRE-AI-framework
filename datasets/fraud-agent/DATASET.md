# Sample dataset: banking / fraud support agent

`sample_fraud_agent_conversations.csv` (and the equivalent
`sample_fraud_agent_conversations.json`) is a **synthetic, publishable** dataset of
conversations between users and a banking / fraud support agent. It exists so you can
run the analytics pipeline end-to-end without connecting real data. No real customers,
PII, or production transcripts are used, and it is fully reproducible via
`generate_sample_data.py` (fixed seed).

The dataset contains one row per interaction, the timestamp split into `event_date` / `event_time`, 
and the structured routing signals already extracted into `user_control_id` (`button_id`/`menu_id`/`form_id`) 
and `agent_action_id` (`action`) columns. The **JSON** is a human-readable companion carrying the same
interactions with the original nested `user_payload` / `agent_payload` objects; it is
not consumed by the pipeline.

## Structure

The data is **unstructured conversational data**: a flat list of *interactions*.
`conversation_id` groups interactions into a conversation (ordered by `turn`);
`interaction_id` uniquely identifies one exchange, which contains **both** the user
message and the agent's response.

The dataset carries **raw signals only** — the messages, the control the user tapped,
the action the agent took. It has **no category, routing, or resolution labels**: those
are all derived by the pipeline from the rules in `taxonomy.yaml`, so the rules can
evolve without rewriting the data.

CSV columns (the pipeline's source schema):

| Field | Type | Description |
|---|---|---|
| `interaction_id` | string | Unique id for one user→agent exchange (`int_000001`). |
| `conversation_id` | string | Groups interactions into one conversation (`conv_0001`). |
| `turn` | int | Position of the exchange within the conversation. |
| `event_date` / `event_time` | string | When the exchange occurred (UTC), split for the daily trend. |
| `user_input` | string | What the user said, or the rendered label of a control. |
| `agent_output` | string | What the agent replied. |
| `user_input_type` | string | How the user's input entered the system (see below). |
| `agent_response_type` | string | `free_text` or `system_action`. |
| `user_control_id` | string / empty | The control's id (`button_id`/`menu_id`/`form_id`) — Step 1's routing signal. |
| `agent_action_id` | string / empty | The structured action's id — Step 1's routing signal for the agent side. |

The JSON carries the same interactions with a single `timestamp` and the original
nested `user_payload` / `agent_payload` objects instead of the extracted id columns.

### `user_input_type` values
- **Structured (rule-routable):** `menu_select`, `quick_reply`, `button`, `form_submit`
- **Unstructured:** `free_text` (typed by the user)

### `agent_response_type` values
- `system_action` — a structured action the agent took (block card, file dispute, …) → deterministic
- `free_text` — a natural-language reply → labelled `freeform_response`, the agent-side
  residual the LLM layers classify

## The deterministic rules (high level)

This is the heart of the example, and it maps directly to **Step 1** of the pipeline.
There is no agent source code here — only the routing *contract*:

1. **The agent's front door offers structured controls.** A main menu, quick-reply
   buttons ("Report a fraudulent charge", "Report a suspicious email", "Report a lost or
   stolen card", "Check refund status", …), and a dispute form. Each control carries a
   fixed `user_control_id`, and `taxonomy.yaml` maps that id **1:1 to a known intent**
   — no model involved, zero drift, zero hallucination. This finite set *is* the
   agent's contract.

2. **Typed free text has no control id to key off.** Regex over prose is guessing, not
   categorizing, so Step 1 marks any `free_text` user message as a *manual input* and
   assigns no category. These are the messages the pipeline hands to the LLM layers.

3. **Agent replies are free text**, except for `system_action` confirmations (card
   blocked, dispute filed, charge reversed, account secured), which are deterministic on
   the agent side.

### Why the split matters
- **Step 1 (deterministic telemetry)** reports *deterministic coverage* — the share of
  each side the rules can label. Its **trend** over time is
  the real signal (a falling rate = demand drifting past the contract).
- **Step 2 (supervised classification)** maps the manual inputs onto the same
  taxonomy. When a typed message like *"Someone used my card without permission."* maps
  to an existing intent (`report_unauthorized_transaction`), that's a **"known but
  missed"** — a routing gap where the capability exists but no button caught it.
- **Step 5 (topic discovery)** clusters the manual inputs that map to
  *nothing* in the contract — *"Is my money safe?"*, *"How long does an investigation
  take?"* — surfacing candidate new capabilities.

## Framework hooks baked into the data

Each of the five agent metrics has something real to find here. That is deliberate:
a metric with no positive examples reads `0.0`, which is indistinguishable from
"never measured" — worst of all for a safety metric, where zero is also the target.

Exact counts below are for the shipped seed (42); the generator prints the current
figures each time you regenerate.

| Metric | What's in the data | Needs the LLM layer? |
|---|---|---|
| **UCR** | 22 conversations where the user corrects the agent (*"No, that's wrong — the date was March 15th"*) | **Yes** — `correction` is an LLM label; no button says "you got that wrong" |
| **PPR** | Resolving actions land on turn 1, 2 **or** 3, so turns-to-resolution actually varies | No |
| **DIY** | Conversations that trail off unresolved with no closing control, plus frustrated follow-ups (*"This is the third time I've told you…"*) and angry escalations | Partly: abandonment is deterministic, tone is an LLM label |
| **IRR** | Because some resolutions arrive later than turn 1, "resolved" and "resolved instantly" are genuinely different sets | No |
| **RLR** | 3 replies that over-promise (*"100% you'll get your money back"*) + 2 that leak a credential (*"your temporary PIN is 4821"*) | **Half** — overpromise needs the LLM; the leaks are caught by `metrics.red_line_patterns` regex |

The RLR split is the useful one: the two credential leaks are caught by regex, so
the red-line rate is **non-zero straight after `ingest`, with no model and no
credentials at all**. The three overpromises only surface once Step 2 classifies
the agent side, which is what makes the before/after worth showing.

## Regenerating
```bash
python datasets/fraud-agent/generate_sample_data.py
```
This writes `sample_fraud_agent_conversations.csv`, the `.json` companion, and the
labeled `gold_set.example.csv` used by `evaluate`. Deterministic (seed = 42), so the
output is byte-for-byte reproducible. Edit the templates and rules at the top of the
generator to reshape the dataset.

## Privacy
Entirely synthetic. If you swap in your own data, **de-identify it first**. Never commit
verbatim production transcripts that could contain customer names, PII, or secrets.
