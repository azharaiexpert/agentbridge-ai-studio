from __future__ import annotations

from app.db import Database


DEFAULT_CHANNELS = ["web", "local-messenger", "whatsapp", "telegram", "slack"]
DEFAULT_MODEL = "llama3.2:3b"


def _agent(db: Database, name: str, role: str, system_prompt: str, tools: list[str], skills: list[str], max_words: int = 180):
    return db.create_agent({
        "name": name,
        "role": role,
        "system_prompt": system_prompt,
        "model": DEFAULT_MODEL,
        "tools": tools,
        "channels": DEFAULT_CHANNELS,
        "schedules": [],
        "memory_enabled": True,
        "skills": skills,
        "interaction_rules": [
            "Use configured tools before answering when relevant.",
            "Generate the final answer using the LLM based on tool evidence.",
            "Keep the response concise, client-ready, and actionable.",
            "Never expose credentials or hidden implementation details.",
        ],
        "guardrails": {"blocked_terms": ["password", "api_key", "secret", "access token"], "max_response_words": max_words, "require_tool_trace": True},
    })


def seed_workspace_data(db: Database) -> None:
    if db.list_agents():
        return

    coordinator = _agent(
        db,
        "Ava Orchestrator",
        "Workflow Coordinator",
        "You are the main orchestrator. Understand the request, classify intent, route work to specialist agents, and maintain the final business objective.",
        ["intent_classifier", "limit_check", "extract_action_items", "compliance_guard"],
        ["routing", "planning", "workflow supervision", "async coordination"],
        170,
    )
    analyst = _agent(
        db,
        "Ravi Task Analyst",
        "Task Analysis Specialist",
        "You analyze user input and prior agent messages. Summarize the problem, identify risk, and produce evidence-backed reasoning for downstream agents.",
        ["summarize_text", "sentiment_check", "calculator", "current_time", "compliance_guard"],
        ["analysis", "summarization", "risk signal detection", "calculation"],
        200,
    )
    action_agent = _agent(
        db,
        "Tara Action Planner",
        "Action Item Specialist",
        "You convert analysis into clear action items with practical owners, priorities, and next steps. Always produce action bullets.",
        ["extract_action_items", "schedule_parser", "notification_draft", "compliance_guard"],
        ["action item extraction", "follow-up planning", "owner assignment", "notification drafting"],
        220,
    )
    reviewer = _agent(
        db,
        "Noah QA Reviewer",
        "Quality and Guardrail Reviewer",
        "You review final outputs for completeness, safe language, actionability, and whether the answer is ready to send.",
        ["policy_risk_check", "compliance_guard", "sentiment_check", "pii_redactor"],
        ["quality review", "guardrails", "compliance", "safe delivery"],
        160,
    )
    messenger = _agent(
        db,
        "Zoya WhatsApp Messenger",
        "WhatsApp Messaging Specialist",
        "You turn approved workflow output into a short WhatsApp-ready response. Use simple language, status, next action, and ask for confirmation.",
        ["notification_draft", "extract_action_items", "sentiment_check", "compliance_guard"],
        ["WhatsApp messaging", "stakeholder update", "short-form communication", "channel delivery"],
        160,
    )

    db.create_workflow({
        "name": "Business Update → Action Items → Review",
        "description": "Orchestrates a business request through analysis, action item extraction, QA review, and final response generation.",
        "entry_node": "orchestrator",
        "max_steps": 4,
        "nodes": [
            {"id": "orchestrator", "label": "Classify & Route", "agent_id": coordinator["id"], "kind": "agent", "x": 80, "y": 120},
            {"id": "analysis", "label": "Analyze Request", "agent_id": analyst["id"], "kind": "agent", "x": 320, "y": 90},
            {"id": "actions", "label": "Extract Actions", "agent_id": action_agent["id"], "kind": "tool-agent", "x": 560, "y": 120},
            {"id": "review", "label": "QA Review", "agent_id": reviewer["id"], "kind": "guardrail", "x": 800, "y": 120},
        ],
        "edges": [
            {"source": "orchestrator", "target": "analysis", "condition": "always", "feedback_loop": False},
            {"source": "analysis", "target": "actions", "condition": "always", "feedback_loop": False},
            {"source": "actions", "target": "review", "condition": "always", "feedback_loop": False},
            {"source": "review", "target": "actions", "condition": "if_negative_sentiment", "feedback_loop": True},
        ],
    })

    db.create_workflow({
        "name": "WhatsApp Support Triage",
        "description": "Handles a conversational channel message, creates action items, reviews safety, and formats a WhatsApp-ready reply.",
        "entry_node": "orchestrator",
        "max_steps": 4,
        "nodes": [
            {"id": "orchestrator", "label": "Triage Message", "agent_id": coordinator["id"], "kind": "agent", "x": 90, "y": 120},
            {"id": "analysis", "label": "Analyze Context", "agent_id": analyst["id"], "kind": "agent", "x": 330, "y": 90},
            {"id": "actions", "label": "Action Plan", "agent_id": action_agent["id"], "kind": "tool-agent", "x": 570, "y": 120},
            {"id": "review", "label": "Safety Check", "agent_id": reviewer["id"], "kind": "guardrail", "x": 810, "y": 90},
            {"id": "messenger", "label": "WhatsApp Reply", "agent_id": messenger["id"], "kind": "channel-agent", "x": 1050, "y": 120},
        ],
        "edges": [
            {"source": "orchestrator", "target": "analysis", "condition": "always", "feedback_loop": False},
            {"source": "analysis", "target": "actions", "condition": "always", "feedback_loop": False},
            {"source": "actions", "target": "review", "condition": "always", "feedback_loop": False},
            {"source": "review", "target": "messenger", "condition": "always", "feedback_loop": False},
        ],
    })

    db.create_workflow({
        "name": "Scheduled Follow-up Workflow",
        "description": "Creates a follow-up plan with schedule recommendation, action items, QA review, and stakeholder notification draft.",
        "entry_node": "orchestrator",
        "max_steps": 5,
        "nodes": [
            {"id": "orchestrator", "label": "Understand Request", "agent_id": coordinator["id"], "kind": "agent", "x": 110, "y": 110},
            {"id": "actions", "label": "Plan Follow-up", "agent_id": action_agent["id"], "kind": "tool-agent", "x": 390, "y": 110},
            {"id": "review", "label": "Review Plan", "agent_id": reviewer["id"], "kind": "guardrail", "x": 670, "y": 110},
            {"id": "messenger", "label": "Notify", "agent_id": messenger["id"], "kind": "channel-agent", "x": 950, "y": 110},
        ],
        "edges": [
            {"source": "orchestrator", "target": "actions", "condition": "always", "feedback_loop": False},
            {"source": "actions", "target": "review", "condition": "always", "feedback_loop": False},
            {"source": "review", "target": "messenger", "condition": "always", "feedback_loop": False},
        ],
    })
