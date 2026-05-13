from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    name: str = Field(..., min_length=2)
    role: str = Field(..., min_length=2)
    system_prompt: str = Field(default="You are a helpful enterprise AI agent.")
    model: str = Field(default="llama3.2:3b")
    tools: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=lambda: ["web"])
    schedules: List[str] = Field(default_factory=list)
    memory_enabled: bool = True
    skills: List[str] = Field(default_factory=list)
    interaction_rules: List[str] = Field(default_factory=list)
    guardrails: Dict[str, Any] = Field(default_factory=lambda: {
        "blocked_terms": ["password", "api_key", "secret"],
        "max_response_words": 140,
        "require_tool_trace": True,
    })


class Agent(AgentConfig):
    id: int
    created_at: datetime
    updated_at: datetime


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[List[str]] = None
    channels: Optional[List[str]] = None
    schedules: Optional[List[str]] = None
    memory_enabled: Optional[bool] = None
    skills: Optional[List[str]] = None
    interaction_rules: Optional[List[str]] = None
    guardrails: Optional[Dict[str, Any]] = None


class WorkflowNode(BaseModel):
    id: str
    label: str
    agent_id: int
    kind: str = "agent"
    x: int = 100
    y: int = 100


class WorkflowEdge(BaseModel):
    source: str
    target: str
    condition: str = "always"
    feedback_loop: bool = False


class WorkflowConfig(BaseModel):
    name: str
    description: str = ""
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
    entry_node: str
    max_steps: int = 8


class Workflow(WorkflowConfig):
    id: int
    created_at: datetime
    updated_at: datetime


class WorkflowRunRequest(BaseModel):
    input: str
    channel: str = "web"
    conversation_id: Optional[str] = None


class ChannelMessage(BaseModel):
    text: str
    user_id: str = "local-user"
    channel: str = "local-messenger"
    agent_id: Optional[int] = None
    workflow_id: Optional[int] = None
    conversation_id: Optional[str] = None


class RunResult(BaseModel):
    conversation_id: str
    workflow_id: Optional[int] = None
    final_answer: str
    steps: List[Dict[str, Any]]
    tokens: int
    estimated_cost_usd: float
    action_items: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    compliance_status: Optional[str] = None


class LogEvent(BaseModel):
    level: str = "INFO"
    event_type: str
    message: str
    conversation_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WhatsAppConfig(BaseModel):
    access_token: Optional[str] = None
    phone_number_id: Optional[str] = None
    whatsapp_business_account_id: Optional[str] = None
    verify_token: Optional[str] = None
    app_secret: Optional[str] = None
    graph_api_version: str = "v21.0"
    test_recipient_number: Optional[str] = None
    auto_reply_enabled: bool = True
    default_workflow_id: Optional[int] = None


class WhatsAppTextMessage(BaseModel):
    to: str
    text: str
    preview_url: bool = False
