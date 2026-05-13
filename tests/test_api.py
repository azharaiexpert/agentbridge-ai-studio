import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["AGENTBRIDGE_DB_PATH"] = "./data/test_agentbridge_ai.db"
os.environ["AGENTBRIDGE_TEST_MODE"] = "true"
Path("./data").mkdir(exist_ok=True)
try:
    Path(os.environ["AGENTBRIDGE_DB_PATH"]).unlink()
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["llm_required"] is True
    assert body["llm"]["available"] is True


def test_agent_creation_and_listing():
    payload = {
        "name": "Test Agent",
        "role": "Tester",
        "system_prompt": "You test API paths.",
        "model": "llama3.2:3b",
        "tools": ["summarize_text"],
        "channels": ["web"],
        "schedules": [],
        "memory_enabled": True,
        "skills": ["testing"],
        "interaction_rules": ["be concise"],
        "guardrails": {"blocked_terms": ["secret"], "max_response_words": 50},
    }
    created = client.post("/api/agents", json=payload)
    assert created.status_code == 201
    assert created.json()["name"] == "Test Agent"
    listed = client.get("/api/agents")
    assert listed.status_code == 200
    assert any(agent["name"] == "Test Agent" for agent in listed.json())


def test_workflow_execution_persists_messages():
    workflows = client.get("/api/workflows").json()
    assert workflows
    workflow_id = workflows[0]["id"]
    run = client.post(f"/api/workflows/{workflow_id}/run", json={"input": "Summarize this issue and create action items", "channel": "web"})
    assert run.status_code == 200
    body = run.json()
    assert body["conversation_id"]
    assert body["steps"]
    messages = client.get(f"/api/messages?conversation_id={body['conversation_id']}")
    assert messages.status_code == 200
    assert len(messages.json()) >= 2


def test_local_channel_delivery():
    res = client.post("/api/channel/message", json={"text": "Create a support action plan", "user_id": "pytest", "channel": "local-messenger"})
    assert res.status_code == 200
    assert "reply" in res.json()
    assert res.json()["conversation_id"]


def test_whatsapp_config_and_status():
    payload = {
        "access_token": "test-token",
        "phone_number_id": "1234567890",
        "whatsapp_business_account_id": "987654321",
        "verify_token": "verify-me",
        "graph_api_version": "v21.0",
        "test_recipient_number": "919999999999",
        "auto_reply_enabled": False,
    }
    saved = client.post("/api/integrations/whatsapp/config", json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert body["access_token"] == "********"
    assert body["phone_number_id"] == "1234567890"
    assert body["is_ready_to_send"] is True

    status = client.get("/api/integrations/whatsapp/status")
    assert status.status_code == 200
    assert status.json()["ready_to_send"] is True


def test_whatsapp_webhook_verification():
    client.post("/api/integrations/whatsapp/config", json={"verify_token": "verify-me"})
    res = client.get("/api/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=12345")
    assert res.status_code == 200
    assert res.text == "12345"


def test_challenge_readiness_scorecard():
    res = client.get('/api/challenge-readiness')
    assert res.status_code == 200
    data = res.json()
    assert data['product'] == 'AgentBridge AI Studio'
    assert data['counts']['agents'] >= 2
    assert data['counts']['workflows'] >= 2
    assert any(item['requirement'] == 'External messaging channel' for item in data['requirements'])
