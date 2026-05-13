# WhatsApp Cloud API Setup

## Minimum fields for outbound messages

| Field | Required | Notes |
|---|---:|---|
| Access Token | Yes | Meta Cloud API token |
| Phone Number ID | Yes | Business/test sender phone number ID |
| Graph API Version | Yes | Example: `v25.0` |
| Test Recipient Mobile | Yes | Personal WhatsApp number, country code only, no `+` or spaces |

## Optional fields

| Field | Purpose |
|---|---|
| WABA / Business Account ID | Useful for account-level operations |
| Verify Token | Required when configuring inbound webhook verification |
| App Secret | Used for webhook signature validation |
| Default Workflow ID | Workflow used for inbound WhatsApp messages |

## UI path

```text
Messaging Channels → WhatsApp Connector Setup
```

## Local webhook URL

For receiving messages locally, expose the server with ngrok or Cloudflare Tunnel.

```text
https://your-public-url/api/integrations/whatsapp/webhook
```

Use the same verify token in Meta and the app UI.
