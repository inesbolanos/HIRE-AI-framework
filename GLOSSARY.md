# Glossary

A comprehensive glossary of terms used in the H.I.R.E. Framework and AI agent development.

## Core Concepts

### AI Agent
A software system that uses artificial intelligence to autonomously perform tasks, make decisions, and take actions on behalf of users. Unlike simple automation or chatbots, agents can reason across ambiguous situations, remember context, and adapt their behavior.

**Example**: a financial fraud analyst agent that investigates suspicious transactions and decides whether to block/allow/investigate.

---

### Agent Washing
The practice of rebranding existing technology as *"AI"* or *"AI agents"* to capitalize on hype, when the technology doesn't actually involve reasoning or decision-making.

**Example**: calling a simple automation script an *"AI agent"* just because it's trendy.

**Historical parallel**: *"Big Data"* hype, where companies called massive Excel files databases.

---

### Automation: rule-based
Software that follows predefined if-then rules to perform tasks. Deterministic and predictable.

**When to use**: For predictable, repeatable tasks with clear rules.

**Example**: 

- Scenario: $2,500 transaction in Tokyo (user normally in NYC)
- Automation: `IF location_change > 500_miles AND amount > $1000 THEN block_transaction`
- AI Agent evaluates:
    - User's travel hisotory (has the user been to Tokyo before?)
    - Purchase type (electronics store vs. luxury goods)
    - Time of day (matches user's timezone or Tokyo timezone?)
    - Other legitimate transactions (pattern of legitimate spending?)

Based on this, agent decides to allow with SMS verification, block or flag for review.

---

### Chatbot: response-based
A conversational interface that retrieves and presents information, but doesn't make decisions or take actions.

**When to use**: For information retrieval and FAQs.

**Example**: 

- Scenario: $2,500 transaction in Tokyo (user normally in NYC)
- AI Agent evaluates:
    - User's travel hisotory (has the user been to Tokyo before?)
    - Purchase type (electronics store vs. luxury goods)
    - Time of day (matches user's timezone or Tokyo timezone?)
    - Other legitimate transactions (pattern of legitimate spending?)

Based on this, agent decides to allow with SMS verification, block or flag for review.

- Chatbot: 
    - Responds to user questions about blocked transactions
    - Retrieves information about why a transaction was flagged
    - Explains policies and procedures
    - BUT cannot take action: can't unblock or investigate


## H.I.R.E. Framework Terms

### H.I.R.E. Framework
A decision framework for evaluating whether to **hire**, **train**, or **fire** an AI agent based on four dimensions:
- **H**uman & Habits
- **I**mpact & Intent
- **R**ules vs. Responses vs. Reasoning
- **E**xposure & Execution

---

### HIRE Decision
The agent passes all evaluation criteria and should be deployed to production with full investment.


---

### TRAIN Decision
The agent shows promise but needs improvement before full deployment. Continue with limited scope or pilot program.


---

### FIRE Decision
The agent is not delivering value and should be discontinued, downgraded (to chatbot or automation), or sunset entirely.

## Metrics & Measurement

### (Fine,) Do It Yourself Rate (DIY)
The percentage of users who start a conversation with the agent but abandon it to solve the problem manually.

**Formula**: `(Sessions Abandoned / Total Sessions) × 100`

**Target**: <20%

**Why it matters**: this is the ultimate churn metric for AI. If users consistently give up, the agent is failing.

---

### Hallucination Rate
How often the agent provides factually incorrect information.

**Target**: <5%

**Why it matters**: trust is destroyed by confident wrong answers.

---
### Instant Resolution Rate (IRR)
The percentage of times users accept the agent's first response without any edits or follow-up questions.

**Why it matters**: This is the gold standard, proving both system accuracy and human trust.

---
### Ping Pong Rate (PPR)
The average number of back-and-forth prompts required before a user gets a satisfactory answer.


**Why it matters**: high ping pong rates indicate inefficient reasoning or poor understanding.

---

### Red Line Rate (RLR)
How often the agent attempts an action that violates security policies, access controls, or safety boundaries.

**Why it matters**: Measures what the agent attempts to get wrong.

---

### Time to Resolution (TTR)
How long it takes to complete a task with the agent vs. without.

**Why it matters**: speed and efficiency is often the core value proposition of agents.

---

### User Correction Rate (UCR)
The percentage of AI-generated output that users need to edit to get what they need.


**Why it matters**: high correction rates indicate the agent isn't providing useful output.


## Technical Concepts

### Deterministic Software
Software that follows strict, predefined rules. The same input always produces the same output.

**Example**: A calculator, a database query, a rule-based automation.

**Analogy**: A train on fixed tracks.

---

### Probabilistic Software
Software that uses patterns and probabilities to generate outputs. The same input may produce different outputs.

**Example**: Large Language Models (LLMs), AI agents, recommendation systems.

**Analogy**: A self-driving car that adapts to changing conditions.

---

### Human-in-the-Loop (HITL)
A design pattern where AI proposes actions, but humans approve execution.

**Example**: a financial fraud AI suggests to block a user but a human must click a button to do it.

**Why it matters**: critical for high-stakes decisions where mistakes are costly.

---

### Human-on-the-Loop (HOTL)
A governance pattern where AI systems act autonomously by default, while a human monitors outcomes and can intervene, pause or override when needed.

**Example**: a financial fraud detection AI auto-blocks transactions above a 0.9 risk socre, while a fraud analyst monitors a live dashboard and can immediatly downgrade

**Why it matters**: balances speed and scale of automation with human oversight for safety, compliance and trust, especially when decision are frequent, time-sensitive, but not high-stake.

---

### Human-out-of-the-Loop (HOOTL)
An autonomous pattern where AI makes and executes decisions end-to-end with no human approval or supervision.

**Example**: a financial fraud detection AI continuously scores transactions and, based on thresholds, auto-allows, challenges or blocks (applying reimbursements and merchant notifications automatically) while humans don't watch live and may only review weekly audit reports or investigate user disputes lately.

**Why it matters**: ultra high-volume, time-critical and relatively low stakes or well-bounded tasks where latency from human involvment would cause more harm than occasional errors. However, there´s an important **risk**: compounding errors, lower explainability. Tight guardrails are needed, audit logs and safe fallbacks.

**Quick decision flow:**
 - If an error is expensive or irreversible: Human-in-the-Loop
 - If speed is crucial but you need a safety net: Human-on-the-Loop
 - If the task is routine, high-volume and well-tuned: Human-out-of-the-Loop

---

### Guardrails
Deterministic safety mechanisms that prevent AI agents from taking dangerous actions.

**Examples**:
- Role-based access control checks
- Command blacklists (e.g., `DROP DATABASE`)
- Rate limiting
- Human approval gates

**Why it matters**: security can never be probabilistic. Guardrails ensure safety even when AI makes mistakes.

---

### Red Line
A security or safety boundary that the agent should never cross.

**Examples**:
- Accessing data without proper permissions
- Executing a blacklisted command
- Requesting sensitive credentials (passwords, API keys)

**Why it matters**: defines the limits of what the agent is allowed to attempt.

---

### Levenshtein Distance (Edit Distance)
The minimum number of single-character edits (insertions, deletions, substitutions) required to change one string into another.

**Example**: 
- String 1: "hello world"
- String 2: "hallo world"
- Distance: 1 (one substitution: e → a)

**Why it matters**: used to calculate User Correction Rate (UCR).

---

### Supervised learning
A machine learning approach where the model is trained on labeled data (input-output pairs).

**Example**: training an LLM to tag transcripts by showing it examples of correctly tagged conversations.

**Use case**: supervised tagging pipeline for classifying agent transcripts.

---

### Unsupervised Learning
A machine learning approach where the model finds patterns in unlabeled data without predefined categories.

**Example**: clustering user prompts to discover common topics or feature requests.

**Use case**: discovering hidden patterns in "out of scope" requests.

---

### NLP (Natural Language Processing)
A field of AI focused on understanding, interpreting, and generating human language.

**Examples**: sentiment analysis, text classification, named entity recognition.

**Use case**: analyzing agent transcripts to understand user sentiment and behavior.

---

### LLM (Large Language Model)
A type of AI model trained on vast amounts of text data to understand and generate human-like language.

**Examples**: GPT-4, Claude, Llama 3.

**Use case**: The "brain" of most AI agents.

---

### RAG (Retrieval-Augmented Generation)
A technique where an LLM retrieves relevant information from a knowledge base before generating a response.

**Example**: a financial fraud agent retrieves takes decisions based on company policies, past user cases, merchant intelligence.

**Why it matters**: reduces hallucinations by grounding responses in real data.

---

### MCP (Model Context Protocol)
A standardized way for AI models to access external tools, data sources, and APIs.

**Why it matters**: allows agents to interact with the real world (databases, APIs).

---

### Fine-Tuning
The process of taking a pre-trained model and training it further on domain-specific data.

**Example**: fine-tuning Llama 3 on your AI agent transcripts to improve tagging accuracy.

**Why it matters**: Improves model performance for specific use cases.

---

### Prompt Engineering
The practice of writing input prompts to get better outputs from LLMs.

**Example**: adding few-shot examples to a tagging prompt to improve classification accuracy.

**Why it matters**: the prompt quality directly impacts the output quality.

---

## Analytics & Data

### Vanity Metrics
Metrics that look impressive but don't measure real business value.

**Examples for AI agents**:
- Number of chat window opens
- Total messages sent
- Session duration (longer ≠ better for AI)
- Buttons clicked

**Why they're misleading**: high activity doesn't mean high value.

---

### Actionable Metrics
Metrics that directly inform decisions and measure business impact.

**Examples for AI agents**:
- User Correction Rate (UCR)
- Ping Pong Rate (PPR)
- Fine, Do It Yourself Rate (DIY)
- Time to Resolution (TTR)

**Why they matter**: these metrics tell if the AI agent is actually improving user experience and removing friction.

---

### Qualitative Data
Non-numerical data like text, conversations, and open-ended feedback.

**Example**: agent transcripts, user comments, feature requests.

**Challenge**: hard to extract insights at scale without structure.

---

### Quantitative Data
Numerical data that can be measured and analyzed statistically.

**Example**: correction rates, session counts, time metrics.

**Challenge**: doesn't capture the "why" behind user behavior.

---

### Structured Data
Data organized in a predefined format, such as tables, JSON.

**Example**: A database table with columns for user_id, timestamp, outcome.

**Why it matters**: Easy to analyze and query.

---

### Unstructured Data
Data without a predefined format such as open response text, images, audio.

**Example**: agent transcripts, user prompts, pictures.

**Challenge**: Requires NLP or other techniques to extract insights.

---

### Confidence Score
A numerical value (0 to 1) indicating how certain a model is about its prediction.

**Example**: an LLM tags a conversation as "resolved" with 0.95 confidence.

**Why it matters**: low confidence scores should trigger human review.

---

### Clustering
A machine learning technique that groups similar data points together without predefined labels.

**Example**: grouping user prompts by topic to discover common feature requests.

**Use case**: unsupervised analysis of agent transcripts.

---

### Sentiment Analysis
Using NLP to determine the emotional tone of text (positive, negative, neutral).

**Example**: detecting frustrated users based on language like *"HELP!!!"* or *"This doesn't work."*

**Use case**: understanding user emotional state during agent interactions.

---

## Business & Strategy

### ROI (Return on Investment)
A measure of the financial return from an investment.

**Formula**: `(Benefit - Cost) / Cost × 100`

**Example**: if an agent costs $300K to build but saves $400K/year, ROI is 33% in Year 1.

**Why it matters**: determines if the agent is worth the investment.

---

### Break-Even
The point at which the cumulative benefits of an agent equal the cumulative costs.

**Example**: If an agent costs $300K to build and saves $30K/month, break-even is 10 months.

**Why it matters**: helps set realistic expectations for when the agent will be profitable.

---

### Change Management
The process of helping people adapt to new tools, processes, or ways of working.

**Example**: training users to trust and use an AI agent instead of traditional processes.

**Why it matters**: cultural change is often harder than technical implementation.

---

### Pilot Program
A limited-scope deployment to test an agent before full rollout.

**Example**: deploying a financial fraud agent for low-value transactions only.

**Why it matters**: reduces risk and allows for iteration based on real feedback.

---

### Blast Radius
The scope of impact if something goes wrong.

**Example**: if an agent fails, does it affect one user, one team, or the entire company?

**Why it matters**: helps assess risk and determine appropriate guardrails.


---

## Acronyms

- **AI**: Artificial Intelligence
- **API**: Application Programming Interface
- **DYI**: Do It Yourself (Rate)
- **HIRE**: Framework to Evaluate AI Agents Need
- **HITL**: Human-in-the-Loop
- **HOTL**: Human-on-the-Loop
- **HOOTL**: Human-out-of-the-Loop
- **IRR**: Instant Resolution Rate
- **KPI**: Key Performance Indicator
- **LLM**: Large Language Model
- **MCP**: Model Context Protocol
- **ML**: Machine Learning
- **NLP**: Natural Language Processing
- **PPR**: Ping Pong Rate
- **RAG**: Retrieval-Augmented Generation
- **RLR**: Red Line Rate
- **ROI**: Return on Investment
- **TTR**: Time to Resolution
- **UCR**: User Correction Rate

## Questions or Additions?

Missing a term? Found an error? Please contribute:
1. Open an issue on GitHub
2. Submit a pull request with the new term
3. Include a clear definition and example


The goal of this glossary is clarity, not jargon. If a term needs a paragraph to explain, it might be too complex.
