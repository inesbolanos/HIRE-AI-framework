# AI Agent Metrics Guide

> **New metrics for the AI era.** Traditional product metrics don't capture the performance of AI agents and what should be improved. A comprehensive set of metrics is suggested below so you can proactively measure and improve your agent performance, to provide the best experience for your users.


| Metric | What It Measures | Good | Warning | Critical |
|--------|-----------------|------|---------|----------|
| **User Correction Rate (UCR)** | How often users edit the agent output | < 15% (simple) > 0.85 (robust) | 15-30% (simple) 0.65-0.85 (robust) | > 30% (simple) <0.65 (robust) |
| **Ping Pong Rate (PPR)** | Repeated questions in same conversation | < 10% | 10-25% | > 25% |
| **Fine, Do It Yourseld Rate (DIY)** | Users abandon agent mid-conversation | < 5% | 5-15% | > 15% |
| **Instant Resolution Rate (IRR)** | Issues solved in ≤ 2 turns | > 60% | 40-60% | < 40% |
| **Red Line Rate (RLR)** | Agent crosses safety/policy boundaries | 0% | > 0% | > 1% |


## User Correction Rate (UCR)

### Definition
The percentage of AI-generated output that users need to edit to get what they need.

Depending on the business need and accuracy impact, the formula can be calculated as a simple correction rate using the Levenshtein Distance or a more robust method such as the Cosine Similarity. Levenshtein Distance considers changes without considering context while Cosine Similarity considers context as well. In real cases, such as fraud or medical chatbots, a robust method may be needed.

**Simple User Correction Rate**: `(Levenshtein Distance / Length of AI Output) × 100`

**Target**: <15%: minor tweaks only

**Robust User Correction Rate**: `cosine_similarity(A, B) = (A · B) / (||A|| x ||B||)`

Where:
- `(A · B)` = dot product of vectors A and B
- `||A||` = length of vector A
- `||B||` = length of vector B
- result will be between -1 and 1

**Target**: >0.70: similar meaning

**Why it matters**: high correction rates indicate the agent isn't providing useful output.

### What counts as a correction?
**Yes:**
- "No, I meant the **blue** one" (color correction)
- "I said **cancel**, not **change**" (action correction)
- "Let me rephrase: I need to..." (explicit rephrase)

**No:**
- Follow-up questions ("What about shipping?")
- New requests ("Also, can you...")
- Confirmations ("Yes, that's correct")

### Calculation Levels

#### **Conversation Level**
```python
ucr_conversation = (corrections_in_conversation / user_messages_in_conversation)
```
**Example:**
- User messages: 8
- Corrections: 2 ("No, I meant refund" + "I said **cancel**")
- UCR: 25%

#### **User Level** (across all conversations)
```python
ucr_user = (total_corrections_by_user / total_user_messages)
```
**Example:**
- User had 5 conversations with 40 total messages
- 6 had corrections
- UCR: 15%

#### **Account Level** (B2B: all users in a company)
```python
ucr_account = (total_corrections_in_account / total_user_messages_in_account)
```
**Example:**
- Account "Acme Corp" has 50 employees
- 200 total conversations, 800 user messages
- 120 corrections
- UCR: 15%

#### **Company-Wide Metric**
```python
ucr_overall = (total_corrections_all_users / total_user_messages_all_users)
```
**Benchmark:** < 15% is healthy, > 30% indicates comprehension issues

## Ping Pong Rate (PPR)

### Definition
The average number of back-and-forth prompts required before a user gets a satisfactory answer.

### Formula
```
Ping Pong Rate = (Repeated Prompts / Total Prompts)
```

**Why it matters**: high ping pong rates indicate inefficient reasoning or poor understanding.

### What Counts as a Repeated Question?
**Yes:**
- "What's my order status?" → [agent responds] → "But what's the **status**?" (same intent)
- "Can I get a refund?" → [agent explains policy] → "So can I get a refund or not?" (unanswered)

**No:**
- "What's my order status?" → "When will it arrive?" (different questions)
- "What's the price?" → "What's the price **with tax**?" (refinement, not repetition)

### Detection Methods
1. **Semantic similarity** (cosine similarity > 0.85 between question embeddings)
2. **Keyword overlap** (> 70% shared keywords)
3. **Secondary LLM usage**

### Calculation Levels

#### **Conversation Level**
```python
ping_pong_rate = (repeated_prompts / total_prompts)
```
**Example:**
- Questions asked: 5
- Repeated: 1 ("What's my balance?" asked twice)
- Ping Pong Rate: 20%

#### **User Level**
```python
ping_pong_rate_user = (total_repeated_prompts / total_prompts_by_user)
```
**Example:**
- User asked 30 questions across 6 conversations
- 4 were repeated
- Ping Pong Rate: 13.3%

#### **Account Level**
```python
ping_pong_rate_account = (repeated_prompts_in_account / total_prompts_in_account)
```

#### **Company-Wide Metric**
```python
ping_pong_rate_overall = (total_repeated_prompts / total_prompts)
```
**Benchmark:** < 10% is healthy, > 25% means agent isn't answering clearly

---

## Fine, Just Do It Yourself Rate (DIY)

### Definition
Percentage of conversations where the user abandons the agent before resolution and completes the task manually (or via human support).

### Formula
```
DIY Rate = (Abandoned Conversations / Total Conversations)
```

### What Counts as Do It Yourself?
**Yes:**
- User says "never mind" / "I'll just do it myself" / "forget it"
- User escalates to human support **without** agent suggesting it
- User completes task via web/app **within 10 minutes** of conversation end (threshold can be adjusted according to context)

**No:**
- Conversation ends with "Thanks!" or confirmation
- Agent successfully hands off to human (intentional escalation)
- User returns later to complete task (> 10 min gap - threshold can be adjusted according to context)
- User stops responding mid-conversation: this is better tracked in a proper inactive session rate

### Calculation Levels

#### **Conversation Level**
```python
abandoned = 1 if (no_resolution or user_stopped_responding) else 0
```
**Binary:** Each conversation is either abandoned (1) or not (0)

#### **User Level**
```python
DIY_rate_user = (abandoned_conversations_by_user / total_conversations_by_user)
```
**Example:**
- User had 10 conversations
- Abandoned 2 (gave up and used web app)
- FIDIM Rate: 20%

#### **Account Level**
```python
DIY_rate_account = (abandoned_conversations_in_account / total_conversations_in_account)
```

#### **Company-Wide Metric**
```python
fidim_rate_overall = (total_abandoned_conversations / total_conversations)
```
**Benchmark:** < 5% is excellent, > 15% means agent is frustrating users

### Advanced Detection
Track **post-conversation behavior**:
- Did user log into web app within 10 min?
- Did user contact support via another channel?
- Did user complete the task manually (e.g., password reset via email)?

---

## Instant Resolution Rate (IRR)

### Definition
Percentage of conversations resolved in **2 turns or fewer** (1 turn = 1 user message + 1 agent response).

### Formula
```
Instant Resolution Rate = (Conversations Resolved in ≤ 2 Turns / Total Conversations)
```

### What Counts as "Resolved"?
**Yes:**
- User confirms resolution ("Thanks!" / "Got it" / "Perfect")
- Task completed (order placed, password reset, refund issued)
- User stops responding **after** agent provides answer (implicit resolution)

**No:**
- User asks follow-up question
- User needs to clarify to get a better answer

### Turn Counting
- **Turn 1:** User asks → Agent responds
- **Turn 2:** User clarifies → Agent closes
- **Turn 3+:** Not instant resolution

### Calculation Levels

#### **Conversation Level**
```python
instant_resolution = 1 if (resolved and turns <= 2) else 0
```
**Binary:** Each conversation is either instant (1) or not (0)

#### **User Level**
```python
instant_resolution_rate_user = (instant_resolutions_by_user / total_conversations_by_user)
```
**Example:**
- User had 8 conversations
- 5 resolved in ≤ 2 turns
- Instant Resolution Rate: 62.5%

#### **Account Level**
```python
instant_resolution_rate_account = (instant_resolutions_in_account / total_conversations_in_account) 
```

#### **Company-Wide Metric**
```python
instant_resolution_rate_overall = (total_instant_resolutions / total_conversations)
```
**Benchmark:** > 60% is excellent, < 40% means agent is too slow/unclear

### Why This Matters
- **User experience:** Fast resolutions = happy users
- **Cost efficiency:** Fewer turns = lower LLM costs
- **Agent capability:** High rate = agent understands common requests

---

## Red Line Rate (RLR)

### Definition
Percentage of agent responses that violate safety, compliance, or policy boundaries.

### Formula
```
Red Line Rate = (Boundary Violations / Total Agent Responses)
```

### What Counts as a Violation?
**Yes:**
- Sharing PII (credit card numbers, SSNs, passwords)
- Making unauthorized promises ("I'll refund you $500")
- Providing medical/legal advice (if not permitted)
- Bypassing authentication ("Sure, I'll reset your password without verification")
- Offensive/biased language
- Hallucinating policies ("We have a 90-day return policy" when it's 30 days)

**No:**
- Politely declining a request ("I can't process refunds over $100")
- Escalating to human ("Let me connect you to a specialist")
- Asking for verification ("Can you confirm your email?")

### Detection Methods
1. **Rule-based:** Regex for PII patterns (SSN, credit cards)
2. **Classifier:** Fine-tuned model to detect policy violations
3. **Human review:** Sample 5-10% of flagged responses
4. **User reports:** "This response was inappropriate" button, manually reviewed

### Calculation Levels

#### **Conversation Level**
```python
red_line_count = number_of_violations_in_conversation
```
**Example:**
- Agent sent 6 messages
- 1 shared a password reset link without verification
- Red Line Count: 1 (16.7% of responses)

#### **User Level**
```python
red_line_rate_user = (violations_in_user_conversations / total_agent_responses_to_user)
```

#### **Account Level**
```python
red_line_rate_account = (violations_in_account / total_agent_responses_in_account)
```

#### **Company-Wide Metric**
```python
red_line_rate_overall = (total_violations / total_agent_responses)
```
**Benchmark:** **0% is the only acceptable target.** Any violation is critical.

### Severity Levels
| Severity | Examples | Action |
|----------|----------|--------|
| **Critical** | PII leak, unauthorized financial action | Immediate escalation, conversation termination |
| **High** | Policy hallucination, bypassing auth | Flag for review, retrain model |
| **Medium** | Inappropriate tone, minor inaccuracy | Log for analysis, no immediate action |

---

## Aggregation Best Practices

### Time Windows
- **Real-time:** Last 24 hours (detect sudden issues)
- **Weekly:** Rolling 7-day average (spot trends)
- **Monthly:** Rolling 30-day average (compare to targets)

### Segmentation
Break down metrics by:
- **Intent type** (refund requests vs. order tracking)
- **User tenure** (new vs. returning users)
- **Time of day** (peak hours vs. off-hours)
- **Agent version** (A/B test prompt changes)

## Target Summary Table

| Metric | Excellent | Acceptable | Needs Improvement | Critical |
|--------|-----------|------------|-------------------|----------|
| **UCR** | < 10% | 10-15% | 15-30% | > 30% |
| **PPR** | < 5% | 5-10% | 10-25% | > 25% |
| **DIY Rate** | < 3% | 3-5% | 5-15% | > 15% |
| **IRR** | > 70% | 60-70% | 40-60% | < 40% |
| **RLR** | 0% | 0% | > 0% | > 1% |

---

## Getting Started

1. **Start with one metric:** Instant Resolution Rate is the easiest to calculate
2. **Instrument your logs:** Ensure you're capturing turn count and resolution status
3. **Set a baseline:** Calculate current performance before making changes
4. **Iterate:** Improve prompts/guardrails, measure impact
5. **Expand:** Add UCR and PPR once you have conversation-level tagging

---

## Related Resources

- [H.I.R.E. Framework](../hire-checklist.md) - Use these metrics in your evaluation
- [Case Study: Incident Management SRE Agent](/case-studies/incident-management-sre-agent.md) - See metrics in action
- [Analytics Architecture](../analytics-architecture/) - How to build the data pipeline *(coming soon)*

---

**Questions?** Open an issue or see [CONTRIBUTING.md](../CONTRIBUTING.md) to share your metric definitions.
