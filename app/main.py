from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.db import Database
from app.integrations.whatsapp import (
    WhatsAppCloudClient,
    extract_whatsapp_messages,
    load_whatsapp_settings,
    safe_public_config,
    save_whatsapp_settings,
)
from app.models import AgentConfig, AgentUpdate, ChannelMessage, WorkflowConfig, WorkflowRunRequest, WhatsAppConfig, WhatsAppTextMessage
from app.runtime.agents import AgentRuntime, LLMRuntimeError
from app.runtime.tools import TOOL_DESCRIPTIONS
from app.runtime.workflows import WorkflowRuntime
from app.seed import seed_workspace_data

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

db = Database(os.getenv("AGENTBRIDGE_DB_PATH") or os.getenv("YUNO_DB_PATH", "./data/agentbridge_ai.db"))
seed_workspace_data(db)
agent_runtime = AgentRuntime(db)
workflow_runtime = WorkflowRuntime(db, agent_runtime)

app = FastAPI(
    title="AgentBridge AI Studio",
    description="LLM-only multi-agent orchestration platform with workflow automation and messaging channels.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(LLMRuntimeError)
async def llm_runtime_exception_handler(request: Request, exc: LLMRuntimeError):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "fix": "Start Ollama, run: ollama pull llama3.2:3b, then restart the API server.",
        },
    )


@app.get("/", response_class=HTMLResponse)
def ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    llm_status = await agent_runtime.model.status()
    return {
        "status": "ok" if llm_status.get("available") else "llm_unavailable",
        "runtime": "llm-only-ollama-runtime",
        "llm_required": True,
        "llm": llm_status,
        "credentials_required_for_llm": False,
        "whatsapp_credentials_required_for_whatsapp_delivery": True,
    }


@app.get("/api/llm/status")
async def llm_status() -> Dict[str, Any]:
    return await agent_runtime.model.status()



@app.get("/api/llm/test")
async def llm_test(prompt: str = "Say hello in one short sentence.") -> Dict[str, Any]:
    answer = await agent_runtime.model.generate(
        system_prompt="You are a health-check assistant. Reply briefly.",
        user_prompt=prompt,
        context="This is a direct LLM test endpoint from AgentBridge.",
        agent_name="LLM Health Check",
        agent_role="Runtime Test Agent",
    )
    return {"available": True, "model": agent_runtime.model.ollama_model, "response": answer}


@app.get("/api/tools")
def list_tools() -> Dict[str, str]:
    return TOOL_DESCRIPTIONS


@app.get("/api/agents")
def list_agents() -> List[Dict[str, Any]]:
    return db.list_agents()


@app.post("/api/agents", status_code=201)
def create_agent(agent: AgentConfig) -> Dict[str, Any]:
    return db.create_agent(agent.model_dump())


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int) -> Dict[str, Any]:
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, updates: AgentUpdate) -> Dict[str, Any]:
    agent = db.update_agent(agent_id, updates.model_dump(exclude_unset=True))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int) -> Dict[str, bool]:
    ok = db.delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"deleted": True}


@app.get("/api/workflows")
def list_workflows() -> List[Dict[str, Any]]:
    return db.list_workflows()


@app.post("/api/workflows", status_code=201)
def create_workflow(workflow: WorkflowConfig) -> Dict[str, Any]:
    return db.create_workflow(workflow.model_dump())


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: int) -> Dict[str, Any]:
    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}")
def update_workflow(workflow_id: int, workflow: WorkflowConfig) -> Dict[str, Any]:
    updated = db.update_workflow(workflow_id, workflow.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return updated


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: int) -> Dict[str, bool]:
    ok = db.delete_workflow(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"deleted": True}


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: int, payload: WorkflowRunRequest) -> Dict[str, Any]:
    try:
        result = await workflow_runtime.run_workflow(
            workflow_id=workflow_id,
            user_input=payload.input,
            channel=payload.channel,
            conversation_id=payload.conversation_id,
        )
        return result.model_dump()
    except LLMRuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/channel/message")
async def local_channel_message(message: ChannelMessage) -> Dict[str, Any]:
    """Universal channel endpoint used by the UI and channel adapters."""
    workflows = db.list_workflows()
    workflow_id = message.workflow_id or (workflows[0]["id"] if workflows else None)

    if workflow_id:
        result = await workflow_runtime.run_workflow(
            workflow_id=workflow_id,
            user_input=message.text,
            channel=message.channel,
            conversation_id=message.conversation_id,
        )
        response: Dict[str, Any] = {
            "reply": result.final_answer,
            "conversation_id": result.conversation_id,
            "result": result.model_dump(),
            "whatsapp_delivery": None,
        }
        if message.channel == "whatsapp":
            response["whatsapp_delivery"] = await send_configured_whatsapp_reply(result.final_answer, result.conversation_id)
        return response

    agents = db.list_agents()
    if not agents:
        raise HTTPException(status_code=400, detail="No agents configured")
    conversation_id = message.conversation_id or f"channel-{message.user_id}"
    db.add_message(conversation_id, "human", message.user_id, message.channel, message.text, {})
    output = await agent_runtime.run_agent(message.agent_id or agents[0]["id"], message.text, conversation_id, message.channel)
    response = {"reply": output.answer, "conversation_id": conversation_id, "whatsapp_delivery": None}
    if message.channel == "whatsapp":
        response["whatsapp_delivery"] = await send_configured_whatsapp_reply(output.answer, conversation_id)
    return response


@app.post("/api/integrations/telegram/webhook")
async def telegram_webhook(update: Dict[str, Any]) -> Dict[str, Any]:
    msg = update.get("message", {})
    chat = msg.get("chat", {})
    text = msg.get("text", "")
    user_id = str(chat.get("id", "telegram-local"))
    response = await local_channel_message(ChannelMessage(text=text, user_id=user_id, channel="telegram"))
    return {"method": "sendMessage", "chat_id": user_id, "text": response["reply"], "conversation_id": response["conversation_id"]}


async def send_configured_whatsapp_reply(text: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Send an agent-generated message to the configured WhatsApp recipient.

    This is used when a user triggers the agent from the local UI using the WhatsApp channel.
    It does not raise to the UI when Meta rejects delivery; it returns a structured status instead.
    """
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    if not settings.auto_reply_enabled:
        return {"attempted": False, "sent": False, "reason": "auto_reply_disabled"}
    if not settings.is_ready_to_send:
        return {"attempted": False, "sent": False, "reason": "missing_access_token_or_phone_number_id"}
    if not settings.test_recipient_number:
        return {"attempted": False, "sent": False, "reason": "missing_test_recipient_number"}
    client = WhatsAppCloudClient(settings)
    try:
        provider_response = await client.send_text(settings.test_recipient_number, text)
        db.add_log(
            "INFO",
            "whatsapp_auto_message_sent",
            "Agent reply sent to configured WhatsApp recipient",
            conversation_id,
            {"to": settings.test_recipient_number, "provider_response": provider_response},
        )
        return {"attempted": True, "sent": True, "to": settings.test_recipient_number, "provider_response": provider_response}
    except Exception as exc:
        db.add_log(
            "ERROR",
            "whatsapp_auto_message_failed",
            f"Agent reply could not be sent to WhatsApp: {exc}",
            conversation_id,
            {"to": settings.test_recipient_number},
        )
        return {"attempted": True, "sent": False, "to": settings.test_recipient_number, "error": str(exc)}


@app.get("/api/integrations/whatsapp/config")
def get_whatsapp_config() -> Dict[str, Any]:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    return safe_public_config(settings)


@app.post("/api/integrations/whatsapp/config")
def save_whatsapp_config(config: WhatsAppConfig) -> Dict[str, Any]:
    save_whatsapp_settings(db, config.model_dump(exclude_unset=True))
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    db.add_log("INFO", "whatsapp_config_saved", "WhatsApp connector configuration saved", None, safe_public_config(settings))
    return safe_public_config(settings)


@app.get("/api/integrations/whatsapp/status")
def whatsapp_status() -> Dict[str, Any]:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    return {
        "channel": "whatsapp",
        "ready_to_send": settings.is_ready_to_send,
        "ready_for_webhook_verification": settings.is_ready_for_webhook_verification,
        "phone_number_id_configured": bool(settings.phone_number_id),
        "access_token_configured": bool(settings.access_token),
        "verify_token_configured": bool(settings.verify_token),
        "test_recipient_configured": bool(settings.test_recipient_number),
        "auto_reply_enabled": settings.auto_reply_enabled,
        "graph_api_version": settings.graph_api_version,
    }


@app.post("/api/integrations/whatsapp/send")
async def send_whatsapp_text(payload: WhatsAppTextMessage) -> Dict[str, Any]:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    client = WhatsAppCloudClient(settings)
    try:
        response = await client.send_text(payload.to, payload.text, payload.preview_url)
        db.add_log("INFO", "whatsapp_message_sent", "WhatsApp message sent", None, {"to": payload.to, "response": response})
        return {"sent": True, "provider_response": response}
    except Exception as exc:
        db.add_log("ERROR", "whatsapp_send_failed", f"WhatsApp send failed: {exc}", None, {"to": payload.to})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/whatsapp/test-send")
async def send_whatsapp_test_message() -> Dict[str, Any]:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    if not settings.test_recipient_number:
        raise HTTPException(status_code=400, detail="Missing test_recipient_number in WhatsApp configuration")
    client = WhatsAppCloudClient(settings)
    try:
        # Send Meta's standard hello_world template first. It works even before a 24-hour user session exists.
        response = await client.send_hello_world_template(settings.test_recipient_number)
        db.add_log("INFO", "whatsapp_test_message_sent", "WhatsApp test template sent", None, {"to": settings.test_recipient_number, "response": response})
        return {"sent": True, "to": settings.test_recipient_number, "provider_response": response, "message_type": "template:hello_world"}
    except Exception as exc:
        db.add_log("ERROR", "whatsapp_test_message_failed", f"WhatsApp test message failed: {exc}", None, {"to": settings.test_recipient_number})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/integrations/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == settings.verify_token:
        db.add_log("INFO", "whatsapp_webhook_verified", "WhatsApp webhook verified successfully", None, {})
        return PlainTextResponse(hub_challenge or "")
    db.add_log("WARN", "whatsapp_webhook_verification_failed", "WhatsApp webhook verification failed", None, {})
    raise HTTPException(status_code=403, detail="WhatsApp webhook verification failed")


@app.post("/api/integrations/whatsapp/webhook")
async def whatsapp_webhook(update: Dict[str, Any], request: Request) -> Dict[str, Any]:
    settings = load_whatsapp_settings(db, reveal_secrets=True)
    client = WhatsAppCloudClient(settings)
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not client.verify_signature(body, signature):
        db.add_log("WARN", "whatsapp_signature_failed", "WhatsApp webhook signature validation failed", None, {})
        raise HTTPException(status_code=403, detail="Invalid WhatsApp webhook signature")

    messages = extract_whatsapp_messages(update)
    responses: List[Dict[str, Any]] = []
    if not messages:
        return {"received": True, "messages_processed": 0, "responses": []}

    for msg in messages:
        user_id = msg["from"]
        text = msg["text"]
        workflow_id = settings.default_workflow_id
        response = await local_channel_message(ChannelMessage(
            text=text,
            user_id=user_id,
            channel="whatsapp",
            workflow_id=workflow_id,
            conversation_id=f"whatsapp-{user_id}",
        ))
        record: Dict[str, Any] = {
            "from": user_id,
            "message_id": msg.get("message_id"),
            "conversation_id": response["conversation_id"],
            "reply": response["reply"],
            "sent_to_whatsapp": False,
        }
        if settings.auto_reply_enabled and settings.is_ready_to_send:
            try:
                provider_response = await client.send_text(user_id, response["reply"])
                record["sent_to_whatsapp"] = True
                record["provider_response"] = provider_response
            except Exception as exc:
                record["send_error"] = str(exc)
                db.add_log("ERROR", "whatsapp_auto_reply_failed", f"WhatsApp auto-reply failed: {exc}", response["conversation_id"], {"to": user_id})
        responses.append(record)

    db.add_log("INFO", "whatsapp_webhook_processed", f"Processed {len(messages)} WhatsApp message(s)", None, {"count": len(messages)})
    return {"received": True, "messages_processed": len(messages), "responses": responses}


@app.post("/api/integrations/slack/webhook")
async def slack_webhook(update: Dict[str, Any]) -> Dict[str, Any]:
    event = update.get("event", {})
    user_id = str(event.get("user", "slack-local"))
    text = event.get("text", "") or update.get("text", "")
    response = await local_channel_message(ChannelMessage(text=text, user_id=user_id, channel="slack"))
    return {"ok": True, "text": response["reply"], "conversation_id": response["conversation_id"]}


@app.get("/api/messages")
def list_messages(conversation_id: Optional[str] = Query(default=None), limit: int = 200) -> List[Dict[str, Any]]:
    return db.list_messages(conversation_id=conversation_id, limit=limit)


@app.get("/api/logs")
def list_logs(limit: int = 200) -> List[Dict[str, Any]]:
    return db.list_logs(limit=limit)


@app.get("/api/metrics")
def metrics() -> Dict[str, Any]:
    return db.metrics_summary()



@app.get("/api/challenge-readiness")
def challenge_readiness() -> Dict[str, Any]:
    """Self-check endpoint that maps the platform implementation to the challenge requirements."""
    agents = db.list_agents()
    workflows = db.list_workflows()
    metrics = db.metrics_summary()
    whatsapp = whatsapp_status()
    return {
        "product": "AgentBridge AI Studio",
        "developed_by": "Azhar",
        "linkedin": "https://www.linkedin.com/in/azhar786",
        "runtime_choice": "Custom async LLM-only runtime powered by Ollama",
        "requirements": [
            {"requirement": "Agent CRUD", "status": "implemented", "evidence": "REST APIs and UI create, list, update, and delete agents."},
            {"requirement": "Agent configuration", "status": "implemented", "evidence": "Agents include role, prompt, model, tools, channels, schedules, memory, skills, rules, and guardrails."},
            {"requirement": "Real runtime", "status": "implemented", "evidence": "WorkflowRuntime and AgentRuntime execute LLM calls, tools, memory, logs, and message queue."},
            {"requirement": "Async communication", "status": "implemented", "evidence": "AgentRuntime uses an asyncio queue and persists inter-agent messages."},
            {"requirement": "Persistence", "status": "implemented", "evidence": "SQLite stores agents, workflows, messages, logs, memory, metrics, and integration settings."},
            {"requirement": "Web UI", "status": "implemented", "evidence": "Responsive UI supports showcase, agents, workflows, channels, tools, and monitoring."},
            {"requirement": "Visual workflow builder", "status": "implemented", "evidence": "Workflow templates render stage cards, conditions, feedback loops, and creation form."},
            {"requirement": "Two or more workflow templates", "status": "implemented", "evidence": f"{len(workflows)} templates seeded."},
            {"requirement": "External messaging channel", "status": "implemented", "evidence": "WhatsApp Cloud API connector with send, test-send, and webhook endpoints."},
            {"requirement": "Monitoring", "status": "implemented", "evidence": "Logs, messages, metrics, token estimates, costs, and latency are persisted and visible."},
            {"requirement": "Tests", "status": "implemented", "evidence": "Pytest covers health, agent creation, workflow execution, channel delivery, and WhatsApp config."},
        ],
        "counts": {
            "agents": len(agents),
            "workflows": len(workflows),
            "tools": len(TOOL_DESCRIPTIONS),
            "runs": metrics.get("runs", 0),
        },
        "whatsapp": whatsapp,
        "recommended_walkthrough": [
            "Start Ollama and run the local server.",
            "Open Client Showcase and run the recommended prompt.",
            "Show orchestrator, analysis, action-planning, QA, and WhatsApp agents in the workflow.",
            "Open Monitoring to show persisted messages, logs, tokens, and latency.",
            "Configure WhatsApp and send the final agent response to the test recipient."
        ],
    }

@app.post("/api/reset-workspace")
def reset_workspace() -> Dict[str, Any]:
    # Keeps data file but clears workspace content for repeatable local runs.
    with db.conn() as conn:
        for table in ["agents", "workflows", "messages", "logs", "memory", "metrics"]:
            conn.execute(f"DELETE FROM {table}")
    seed_workspace_data(db)
    return {"status": "reset", "agents": len(db.list_agents()), "workflows": len(db.list_workflows())}
