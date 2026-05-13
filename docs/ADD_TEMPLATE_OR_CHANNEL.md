# Add Templates or Channels

## Add a workflow template

Use the UI:

1. Open **Workflow Builder**.
2. Click **Create New Template**.
3. Enter name, description, and type.
4. Click **Save Template**.

Or use the API:

```http
POST /api/workflows
```

Payload must include:

- `name`
- `description`
- `nodes`
- `edges`
- `entry_node`
- `max_steps`

## Add a messaging channel

1. Create a new integration adapter endpoint in `app/main.py`.
2. Parse the external payload.
3. Convert it to `ChannelMessage`.
4. Call the same runtime used by WhatsApp:

```python
await local_channel_message(ChannelMessage(...))
```

This preserves one runtime for web, WhatsApp, Telegram-style, Slack-style, and future channels.
