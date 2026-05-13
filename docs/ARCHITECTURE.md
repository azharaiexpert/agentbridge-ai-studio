# Architecture

```mermaid
flowchart LR
    UI[Responsive Web UI] --> API[FastAPI Backend]
    API --> DB[(SQLite)]
    API --> Runtime[Custom Async Agent Runtime]
    Runtime --> LLM[Ollama LLM]
    Runtime --> Tools[Tool Registry]
    Runtime --> Bus[Async Message Queue]
    Bus --> Agents[Configurable Agents]
    API --> WhatsApp[WhatsApp Cloud API]
    Runtime --> Monitoring[Logs / Metrics / Messages]
    Monitoring --> DB
```

## Layers

| Layer | Files | Responsibility |
|---|---|---|
| UI | `app/static/index.html` | Agents, workflows, WhatsApp setup, monitoring |
| API | `app/main.py` | REST endpoints, WhatsApp webhook, readiness scorecard |
| Runtime | `app/runtime/agents.py`, `app/runtime/workflows.py` | LLM execution, tool execution, async agent routing |
| Tools | `app/runtime/tools.py` | Summarization, action extraction, compliance, scheduling, notification draft, calculator |
| Persistence | `app/db.py` | SQLite schema and data access |
| Integrations | `app/integrations/whatsapp.py` | WhatsApp Cloud API client and config handling |
