# Runbook

## Ollama not found

Install Ollama and reopen the terminal.

## ModuleNotFoundError: app

Run from project root:

```powershell
$env:PYTHONPATH="."
python scripts\seed_workspace.py
```

## Action items not visible

The final version returns `action_items` directly from workflow execution. Check the Full JSON panel and Monitoring logs.

## WhatsApp not received

1. Use digits only for recipient: `91XXXXXXXXXX`.
2. Send Meta's test message first from API Setup.
3. Confirm token and phone number ID.
4. Use the UI **Send Test Message**.
5. Check `/api/logs?limit=20`.
