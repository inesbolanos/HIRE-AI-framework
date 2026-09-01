# AI Agent Metrics Guide

> **New metrics for the AI era.** Traditional product metrics don't capture the performance of AI agents and what should be improved. A comprehensive set of metrics is suggested below so you can proactively measure and improve your agent performance, to provide the best experience for your users.

These metrics are calculated from the pipeline's output, so run the pipeline first.

| Metric | The question it answers | Good | Warning | Critical |
|--------|------------------------|------|---------|----------|
| **User Correction Rate (UCR)** | How often users edit the agent output | < 15% | 15-30% | > 30% |
| **Ping Pong Rate (PPR)** | Back-and-forths until the user actually gets the right answer | ≤ 1.2 turns | 1.2-2.0 turns | > 2.0 turns |
| **Fine, Do It Yourself Rate (DIY)** | Users abandon the conversation and do the action in the traditional UI | < 5% | 5-15% | > 15% |
| **Instant Resolution Rate (IRR)** | Issues solved in the first turn | > 60% | 40-60% | < 40% |
| **Red Line Rate (RLR)** | Agent crosses safety/policy boundaries | 0% | 0-1% | > 1% |

Read them together, not individually. UCR and IRR measure **precision**; PPR measures **efficiency**; DIY is the **churn** signal; RLR is the **safety** gate. A high IRR with a high DIY rate means the agent is excellent at the narrow set of things it handles but useless at everything else.

## User Correction Rate (UCR)

### Definition
How much of the agent's output the user has to delete or rewrite before it actually solves their problem.

This is a **precision** metric measured by *volume of rework*. A low correction rate means high precision.

### Formula
  The interactions when a user corrects the agent are labeled based on *correction_categories* from *taxonomy.yaml*
```
conversations_with_a_correction = any(intent in correction_categories)
user_correction_rate = conversations_with_a_correction / all_conversations
```

**Why it matters**: high correction rates mean the user is doing the work the agent was supposed to do. The output is a draft, not an answer.

### What counts as a correction?
**Yes:**
- "No, I meant the **blue** one" (color correction)
- "I said **cancel**, not **change**" (action correction)
- "Let me rephrase: I need to..." (explicit rephrase)
- Editing the agent's proposed text, command, or config before using it

**No:**
- Follow-up questions ("What about shipping?")
- New requests ("Also, can you...")
- Confirmations ("Yes, that's correct")

## Ping Pong Rate (PPR)

### Definition
The average number of back-and-forth prompts until the user actually gets the correct answer or executes the fix.

This is an **efficiency** metric measured as an *average turn count, not a percentage*. The target is close to 1.

### Formula
For each resolved conversation, the user's request maps to an expected agent output (*intent_resolving_actions* in *taxonomy.yaml*). 
PPR is the turn on which that output arrived, averaged over the conversations that were resolved.
```
ping_pong = first turn where the agent takes an action that resolved a stated intent
ppr = mean(ping_pong) over resolved conversations
```

**Clarifying questions currently count.** An agent that asks one useful question and then resolves scores 2.0, the same as one where the user had to repeat themselves — PPR measures *elapsed* exchanges, not *wasted* ones. To exclude them you would identify clarification exchanges by their category labels (`gather_information` / `provide_transaction_details` and friends) and skip those turns; the shipped implementation does not, so read PPR next to IRR rather than alone.

**Why it matters**: a high ping pong rate means inefficient reasoning, poor initial understanding and added user effort. A rising PPR alongside a *rising* IRR can be fine — the agent is asking one good question instead of guessing. A rising PPR alongside a *falling* IRR is the bad case.

### The denominator matters
Average **only over conversations that actually reached a resolution.** Conversations that never got there aren't slow, they failed, and they're already counted in the DIY rate. Including them here would both skew the average and punish the same failure twice.

### What counts as reaching the answer?
**Yes:**
- A structured action that resolves a stated intent (card blocked, dispute filed, account secured)
- The **first** such action, when several occur — resolving early is what's rewarded

**No:**
- The agent gathering information — nothing was resolved yet, but the turn still counts toward the average
- Free-text reassurance with no action behind it
- An action unrelated to what the user asked for
- Informational asks with no resolving action defined: not resolvable, so excluded entirely

## Fine, Just Do It Yourself Rate (DIY)

### Definition
How often users abandon the chat or go execute the action in the traditional UI instead.

**This is the ultimate churn metric for AI agents.** Every other metric measures how well the agent performed; this one measures whether users still believe in it.

### Formula
```
diy_conversations = conversation not resolved and (not ended or frustration or escalation)
diy_rate = diy_conversations / all_conversations
```
The variables *frustration_tones* and *escalation_categories* are defined in *taxonomy.yaml*
The true definition needs also product telemetry: did the user do the same thing in the UI after giving up?
Binary: each conversation is either DIY (1) or not (0)

**Why it matters**: this metric measures **agent trust**, not performance.

### What counts as do-it-yourself?
**Yes:**
- User says "never mind" / "I'll just do it myself" / "forget it" (explicit abandonment)
- User completes the same task via the web/app UI **within 10 minutes** of the conversation ending (threshold can be adjusted according to context)
- User escalates to human support **without** the agent suggesting it
- Dropping out mid-request, never getting the correct action/answer, never closing cleanly

**No:**
- Conversation ends with "Thanks!" or confirmation
- Agent successfully hands off to a human (intentional escalation)
- User returns later to complete the task (> 10 min gap — threshold can be adjusted according to context)
- User stops responding mid-conversation: this is better tracked in a proper inactive session rate

## Instant Resolution Rate (IRR)

### Definition
How often the agent gives an accurate answer outright: no edits, no follow-up questions, no alternative actions in the UI.

This is the **accuracy and trust** metric and the strictest of all. A conversation only counts if the agent got it right the first time.

### Formula
```
# resolvable = the conversation had at least one intent with a non-empty entry in
# rules.intent_resolving_actions. Informational asks are excluded from the denominator, 
# not counted as failures.
instant_resolution = conversation_resolved and turns_to_resolution == 1
irr                = instant_resolution_conversations / resolvable_conversations
```
The denominator is **resolvable** conversations, not resolved ones. Dividing by
*resolved* would ask "of the ones we fixed, how many were instant", which hides
every actionable request the agent never resolved at all, and can read high while
the agent is failing.

**Why it matters**: users extend trust to an agent that is right the first time, and withdraw it fast once they have to check its work. A high IRR is what makes the agent feel like an answer rather than a first draft. Keeping this metric high also means reducing LLM costs.

### What counts as an instant resolution?
**Yes:**
- The resolving action landed on the very first exchange
- Task completed (order placed, password reset, refund issued) with nothing further needed

**No:**
- User edited the output before using it (that's UCR)
- User asked a follow-up or clarifying question (that's PPR)
- User went to the UI to finish the job (that's DIY)
- Informational asks with no resolving action: not in the denominator at all

## Red Line Rate (RLR)

### Definition
How often the agent executes an action or suggests a command that hits a guardrail, fails a security check, or gets blocked.

This is the **safety** gate and it measures **attempted** mistakes: a guardrail that catches a dangerous action is a system working correctly, and a signal that the agent tried. Both facts matter: the block protected the user, and the attempt tells you what the agent would have done unsupervised.

This is the only metric evaluated **per interaction** rather than per conversation. 

### Formula
```
rlr_interactions = (llm_output_category in red_line_categories) or (red_line_patterns matches agent_output)
rlr =  rlr_interactions / total interactions
```

*red_line_categories* and *red_line_patterns* are defined in *taxonomy.yaml*
Red line categories catch judgment failures, red line patterns catch mechanical leaks (need to be double checked when happening).

**Why it matters**: a red line is a compliance event and the attempt tells you what the agent would have done unsupervised.

### What counts as a red line?
**Yes:**
- A suggested command that fails a security check or is refused by policy
- Attempting an action beyond the agent's authorization (bypassing authentication, acting without verification)
- Sharing PII (credit card numbers, SSNs, passwords)
- Making unauthorized promises ("I'll refund you $500", "100% you'll get your money back")
- Hallucinating policies ("We have a 90-day return policy" when it's 30 days)
- Offensive/biased language

**No:**
- Politely declining a request ("I can't process refunds over $100")
- Escalating to a human ("Let me connect you to a specialist")
- Asking for verification ("Can you confirm your email?")

### Severity Levels
Track the mix, not just the count.

| Severity | Examples | Action |
|----------|----------|--------|
| **Critical** | PII leak, unauthorized financial action, executed destructive command | Immediate escalation, conversation termination |
| **High** | Policy hallucination, attempted auth bypass (blocked) | Flag for review, retrain model |
| **Medium** | Inappropriate tone, minor inaccuracy, over-broad suggestion | Log for analysis, no immediate action |

---

## Aggregation Best Practices

### Calculation levels
Every metric above is defined over a population of conversations (RLR: interactions). Swap the population to get a per-user or per-account figure, the formula itself doesn't change:

```
ucr_user    = user_conversations_with_a_correction / total_conversations_for_the_user
ucr_account = account_conversations_with_a_correction / total_conversations_for_the_account
```

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

**Questions?** Open an issue or see [CONTRIBUTING.md](../../CONTRIBUTING.md) to share your metric definitions.
