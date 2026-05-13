# AgentBridge AI Studio - Submission Notes

## Repository contents

This repository contains the final working implementation of AgentBridge AI Studio for the AI Agent Orchestration Platform challenge.

Key folders:

- `app/` - FastAPI backend, web UI, LLM agent runtime, tools, workflows, SQLite persistence, and WhatsApp integration
- `scripts/` - workspace seeding and local helper scripts
- `tests/` - critical path tests for agent creation, workflow execution, and channel delivery
- `docs/` - architecture, setup, WhatsApp setup, extension notes, runbook, and submission documentation
- `docs/submission/` - final PDF/DOCX files for upload

## Main submission files

- `README.md`
- `docs/submission/AgentBridge_AI_Studio_Documentation_of_Understanding.pdf`
- `docs/submission/AgentBridge_AI_Studio_Setup_and_Run_Guide.pdf`

## Local run summary

```powershell
ollama pull llama3.2:3b
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts\seed_workspace.py
$env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
$env:OLLAMA_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="llama3.2:3b"
$env:OLLAMA_TIMEOUT_SECONDS="240"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Suggested GitHub repository name

```text
agentbridge-ai-studio
```
