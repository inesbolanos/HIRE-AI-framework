# HIRE-AI
The H.I.R.E AI framework: templates and metrics for evaluating and measuring AI Agents performance
# The H.I.R.E. Framework: Analytics-Driven AI Agent Evaluation


> **When to Hire, Train or Fire Your AI Agent.**
> A strategic playbook and analytics toolkit for evaluating, building, and measuring the real business impact of AI Agents.


[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)


## About This Repository


This repository is an **open-source implementation** of the H.I.R.E. Framework, presented at [Data & AI Tech Summit 2026](https://dataiwarsaw.tech/). It provides product teams, data analysts, and engineering leaders with structured tools to:




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
* **`/case studies` :** includes a template to share real-world case studies written by the community, how the H.I.R.E. framework was applied, and key learnings. Check how to [contribute](CONTRIBUTING.md) with yours.




## Quick Start


1. **Evaluate your agent idea:** start with the H.I.R.E. checklist to determine if an AI agent is the right solution.
2. **Choose your metrics**: review the AI Agent Metrics Guide and select the KPIs that align with your business goals.


## Coming Soon
- **Code examples:** metric calculation scripts for each metric.
- **Sample datasets**: conversation logs to be used for testing.
- **Analytics Pipeline**: supervised tagging and unsupervised clustering workflows.
- **Agent Evaluation:** script to generate summary of metrics and findings to evaluate agent performance.


### Prerequisites
- Python 3.9+
- Access to conversational data (chat transcripts, logs)
- A data warehouse (Snowflake, BigQuery, Redshift, etc.)
- (Optional) A self-hosted LLM for transcript tagging (e.g., Llama 3). This ensures privacy for sensitive data.


## Key Metrics for AI Agents
The shift from deterministic to probabilistic software requires a shift in analytics as well. We need to stop measuring clicks and start measuring friction removed. This framework introduces the following metrics:


| Metric | What It Measures | Why It Matters |
|--------|------------------|----------------|
| **User Correction Rate (UCR)** | How much of the AI's output users edit before accepting | Low edits = high trust and accuracy |
| **Ping Pong Rate (PPR)** | Average back-and-forth prompts before resolution | Lower is better, but allow room for clarifying questions |
| **Fine, Do It Yourself Rate (DIY)** | % of users who solve the task in the traditional way | Ultimate churn metric for AI Agents |
| **Instant Resolution Rate (IRR)** | % of first responses accepted without edits | Measures both accuracy and trust |
| **Red Line Rate (RLR)** | How often the agent attempts unsafe actions | Critical for security and compliance |


See the [agent-metrics-calculation](/framework/agent-metrics/ai-agent-metrics.md) for implementation details.


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


Read the full case study: [case-studies/incident-management-sre-agent.md](/case-studies/incident-management-sre-agent.md)


## When NOT to Build an AI Agent


This framework will help you **fire** agents that shouldn't exist:


- The problem occurs less than 10 times per year (low ROI)
- A simple automation rule can solve it (don't take the high-speed train, just walk).
- The cost of a mistake is catastrophic (e.g., life-or-death scenarios)
- Your team isn't ready to trust AI in this workflow (cultural resistance)
- You can't build deterministic safety guardrails (security risk)


**Having the courage to fire an agent is what makes great product strategy.**


## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. Feel free to use these templates in your own company's workflows.


Created by Inês Bolaños, Senior Product Analyst at PagerDuty [say hi! on LinkedIn](https://www.linkedin.com/in/inesbolanos/). Based on real-world experience evaluating AI Agents. Special thanks to the data and engineering teams who helped shape these ideas and to the community for contribution to this open-source project.


