# H.I.R.E. Framework Checklist

Use this checklist to evaluate whether an AI agent is the right solution for your business problem. Each section corresponds to one letter of the H.I.R.E. framework.

In some sections, the decision is go no go, while in others the decision is defined by a scoring. In the end of this checklist you should have a comprehensive info that helps you take the hire, train or fire decison.


## **H** - Human & Habits

### Cultural Readiness
- [ ] **Trust assessment**: will users trust AI recommendations in this process?
  - Consider: is this a high-stakes decision? Are users skeptical of automation?
  - Scoring: 1-low trust/2-medium trust/3-high trust

- [ ] **Cultural fit**: What is the users knowledge and acceptance of AI tools?
  - Consider: technical experience, self-serve problems
  - Scoring: 1-low fit/2-medium fit/3-high fit

- [ ] **User control**: Can users edit, correct, or override the agent's decisions?
  - Consider: editable memory, undo functionality, manual override options
  - Scoring: 1-low control/2-medium control/3-high control

- [ ] **Change management plan**: do we have a plan to onboard users to this new workflow?
  - Consider: training materials, gradual rollout, feedback loops
  - Scoring: 1-low/2-medium/3-high

### Infrastructure Readiness
- [ ] **Data quality**: is our historical data clean enough to train/inform the agent?
  - Consider: Garbage in = garbage out. Poor data = poor agent performance
  - Scoring: 1-low quality/2-medium quality/3-high quality
  
- [ ] **System integration**: can the agent access the tools and data it needs?
  - Consider: API access, authentication, data pipelines
   - Scoring: 1-low integration/2-medium integration/3-high integration
  
- [ ] **Interaction with user**: Will the agent be proactive or reactive?
  - Consider: agents should act like teammates, not search bars
  - Scoring: 1-reactive/2-mixed/3-proactive

### Red Flags:
- Users are resistant to automation in this area
- Historical data is incomplete, inconsistent, or outdated
- No plan for user training or change management

### Score: /21

## **I** - Impact & Intent

### Intent Check
- [ ] **Need vs. Hype**: are we building this because of a clear business need or just industry hype?
  - If you can't clearly articulate the business problem, **STOP**.

### Job Description Exercise
- [ ] **Role Definition**: can you write a clear job description for this agent?
  - Title: _______________________
  - Key Responsibilities: _______________________
  - Boundaries (what it CANNOT do): _______________________
  
- [ ] **Performance Review**: how will you measure this agent's success? What target do you plan to achieve for each?
  - KPI 1: _______________________
  - KPI 2: _______________________
  - KPI 3: _______________________

  If you can't define the job description and metrics of success, **STOP**

### ROI Calculation
- [ ] **Problem Frequency**: how often does this problem occur?
  - Scoring: 1-annualy, 2-quarterly, 3-monthly, 4-weekly, 5-daily
  
- [ ] **Time Savings**: how much time will the agent save for this process?
  - Current time to resolve: _______ minutes/hours
  - Expected time with agent: _______ minutes/hours
  - Time saved per process: _______ minutes/hours

  - Scoring: 1: 0-10% time saved/2: 11-20% time saved/3: 21-50% time saved/4: more than 50% time saved
  
- [ ] **ROI**: does the benefit of the agent justify the investment?
  - Engineering cost to build: _______
  - Ongoing maintenance cost: _______
  - Expected annual savings: _______
  - Break-even timeline: _______
  - ROI: _______
- Scoring: -5: negative ROI/0: neutral/5: positive ROI

- [ ] **Strategical value**: besides financial impact, is there any strategical value from this agent?
  - Consider: positioning, competitor advantage, high-impact customer need
  - Scoring: 1-low/2-medium/3-high

### Red Flags
- Problem occurs less than 10 times per year (low ROI)
- Can't write a clear job description
- Building *"because everyone else has AI"*

### Score: /17


## **R** - Rules vs. Responses vs. Reasoning

### Task Classification

**Is the task predictable and rule-based?**
- [ ] YES → You need **automation** (if-then rules), not an AI agent
- [ ] NO → Continue to next question

**Is the task purely informational (answering questions, summarizing)?**
- [ ] YES → You need a **chatbot** (retrieval-based responses), not an AI agent
- [ ] NO → Continue to next question

**Does the task involve:**
- [ ] Ambiguity and context-dependent decisions?
- [ ] Multi-step reasoning across fragmented information?
- [ ] Remembering intermediate states?
- [ ] Retrying when errors occur?
- [ ] Adapting to changing conditions?

If you checked 3+ boxes above, you likely need an **AI agent**.

| Approach | What It Would Do | Why It's Not Enough |
|----------|------------------|---------------------|
| **Rule** | Explain what automation would do instead of an AI Agent | Why automation doesn't solve this problem
| **Chatbot** | Explain what a chatbot would do instead of an AI Agent | Why a chatbot doesn't solve this problem |

### Red Flags
- Using an agent for a simple rule-based task
- Expecting a chatbot to reason and make decisions
- No clear distinction between what's automated vs. what requires reasoning

## **E** - Exposure & Execution

### Risk Assessment

**If this agent makes the worst possible mistake, what happens?**
- [ ] Minor inconvenience (e.g., wrong email sent)
- [ ] Moderate impact (e.g., temporary service disruption)
- [ ] Severe impact (e.g., data loss, security breach)
- [ ] Catastrophic impact (e.g., life-or-death, legal liability)

**If you selected "Catastrophic impact," DO NOT BUILD THIS AGENT.** For the other cases, implement strict guardrails.
- Scoring: -1: minor inconvenience/-10: moderate impact/-20: severe impact

### Guardrails & Safety

- [ ] **Human-in-the-Loop**: does a human approve critical actions before execution?
  - Consider: approval workflows, confirmation dialogs, audit trails
  - Scoring: -5: none/0: partial/5: ensured
  
- [ ] **Deterministic Security**: are security checks handled by rules, not AI?
  - Consider: Role-based access control (RBAC), command blacklists, permission checks
  - Scoring: -5: AI/5: rules
  
- [ ] **Rollback Capability**: can we undo the agent's actions if something goes wrong?
  - Consider: version control, backup systems, manual override
  - Scoring: -5: no/5: yes
  
- [ ] **Audit Trail**: do we log every action the agent takes or suggests?
  - Consider: compliance, debugging, accountability
  - Scoring: -5: no/5: yes

- [ ] **Tenant Isolation**: data is not used for cross customer learning
  - Consider: isolated action
  - Scoring: -5: no/5: yes

Note: if some of the guardrails don't apply to your use case, adjust the score accordingly

### Execution Boundaries

- [ ] **Read-Only vs. Write Access**: does the agent only suggest, or can it execute?
  - Suggestion-only = lower risk
  - Execution = requires strict guardrails
  - Scoring: -10: write access/10: read-only
  
- [ ] **Failure Mode**: what happens if the agent is unavailable?
  - Can users complete the task manually?
  - Is there a fallback system?

  - Scoring: -5: no fallback system/5: fallback system

Note: if some of the execution boundaries don't apply to your use case, adjust the score accordingly

### Red Flags
- No human approval for high-stakes actions
- Security decisions are made probabilistically by AI
- No rollback or undo capability
- Catastrophic failure would cause irreversible harm

### Score : -60/40

### Overall Assessment
- Total H.I.R.E. score <30:  **DO NOT BUILD,** evaluate alternative solutions
- Total H.I.R.E. score 31-50:  **TRAIN,** improve weaknesses
- Total H.I.R.E. score >50:  **HIRE,** an AI Agent is the right solution

### When we would FIRE this agent:
Deprecation criteria examples:
- User correction rate (UCR) spikes
- Ping Pong Rate (PPR) constantly high
- Do It Yourself Rates (DIY) above 70% x months after launch
- Red Line Rate (RLR) above 20% (this threshold should be defined based on the risk tolerance)
- Maintenance costs exceed value delivered
- A better solution is available

### Alternative Solutions

If you decided to FIRE the agent, consider:
- **Automation**: can a simple rule-based system solve this?
- **Chatbot**: do users just need information retrieval?
- **Human Process Improvement**: can we optimize the manual workflow instead?
- **Wait**: is the technology/data/culture not ready yet? Revisit in a few months.

## Documentation

Once you've completed this checklist, document your decision:

**Agent Name**: _______________________

**Decision**: HIRE / TRAIN / FIRE

**Rationale**: 
_______________________

**Next Steps**:

**Review Date**: _______ (Revisit this decision in 3-6 months)


## Stakeholder Sign-Off

Before proceeding, ensure alignment across teams:

- [ ] Product Manager: _______________________
- [ ] Engineering: _______________________
- [ ] Data/Analytics: _______________________
- [ ] Security/Compliance: _______________________
- [ ] End Users Representative: _______________________

**Remember**: having the courage to FIRE an agent before building it is what makes great product strategy.