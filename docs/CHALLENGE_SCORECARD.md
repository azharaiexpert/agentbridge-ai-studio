# Challenge Scorecard

| Requirement | Status | Evidence |
|---|---|---|
| Configurable agents | Complete | Agent CRUD UI + API supports role, prompt, model, tools, channels, schedules, memory, skills, rules, guardrails |
| Real runtime | Complete | Custom async LLM-only runtime calls Ollama and executes real tools |
| Async agent communication | Complete | Inter-agent messages are sent through an asyncio queue and persisted |
| Persistence | Complete | SQLite stores agents, workflows, messages, logs, memory, metrics, integration settings |
| External messaging | Complete | WhatsApp Cloud API connector with setup UI, test send, send endpoint, and webhook verification |
| Visual builder | Complete | Template list, stage rendering, create-template form, conditions and feedback loops |
| 2+ templates | Complete | Three seeded templates |
| Live monitoring | Complete | UI shows logs, messages, token estimates, run count, and latency metrics |
| Tests | Complete | Pytest covers critical paths |

## Recommended walkthrough

1. Start Ollama and the FastAPI app.
2. Open Agents and show the five specialist agents.
3. Open Workflow Builder and run `Business Update → Action Items → Review`.
4. Verify final answer, action items table, sentiment, compliance, and full JSON.
5. Open WhatsApp Channel, save connector config, and send the final agent reply.
6. Open Monitoring to show persisted logs and inter-agent messages.
