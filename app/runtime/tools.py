from __future__ import annotations

import ast
import math
import operator
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List


class ToolExecutionError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    return max(1, int(len(str(text).split()) * 1.3))


def safe_calculator(expression: str) -> str:
    allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }
    allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Name) and node.id in allowed_names:
            return allowed_names[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in allowed_names:
            args = [_eval(arg) for arg in node.args]
            return allowed_names[node.func.id](*args)
        raise ToolExecutionError("Unsafe or unsupported calculator expression")

    tree = ast.parse(expression, mode="eval")
    result = _eval(tree.body)
    return str(round(result, 6) if isinstance(result, float) else result)


def summarize_text(text: str, max_sentences: int = 3) -> str:
    text = (text or "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return "No text provided to summarize."
    if len(sentences) == 1 and len(sentences[0]) > 380:
        return sentences[0][:380].rstrip() + "..."
    return " ".join(sentences[:max_sentences])


def intent_classifier(text: str) -> str:
    lower = text.lower()
    labels: List[str] = []
    if any(k in lower for k in ["whatsapp", "notify", "message", "send", "reply"]):
        labels.append("messaging")
    if any(k in lower for k in ["action", "todo", "task", "owner", "next step", "plan"]):
        labels.append("action_planning")
    if any(k in lower for k in ["risk", "issue", "failed", "delay", "blocked", "urgent", "critical"]):
        labels.append("incident_or_risk")
    if any(k in lower for k in ["summary", "summarize", "update", "report", "manager", "client"]):
        labels.append("business_summary")
    if any(k in lower for k in ["schedule", "remind", "daily", "weekly", "tomorrow", "follow up"]):
        labels.append("schedule_or_follow_up")
    return ", ".join(labels or ["general_orchestration"])


def extract_action_items(text: str) -> str:
    """Return deterministic, visible action items so the UI always has a structured table."""
    lower = text.lower()
    items: List[str] = []

    def add(item: str) -> None:
        if item not in items:
            items.append(item)

    if any(k in lower for k in ["failed", "error", "issue", "delay", "blocked", "memory", "risk", "critical"]):
        add("Investigate the root cause and capture the failure summary")
        add("Assign an owner to validate the fix and confirm stability")
    if any(k in lower for k in ["memory", "executor", "emr", "spark", "cluster"]):
        add("Review resource configuration and update the runbook")
        add("Add monitoring alerts for resource pressure before failure")
    if any(k in lower for k in ["s3", "output", "generated", "completed", "success"]):
        add("Share the generated output location with stakeholders for validation")
    if any(k in lower for k in ["whatsapp", "notify", "send", "message", "reply", "manager", "client"]):
        add("Prepare and send a concise stakeholder update")
    if any(k in lower for k in ["schedule", "follow up", "eta", "tomorrow"]):
        add("Schedule a follow-up checkpoint with ETA and owner")
    if not items:
        add("Clarify objective, expected output, owner, and delivery timeline")
        add("Run the configured workflow and review the final response")
        add("Share the approved response through the selected channel")

    return "\n".join(f"- {item}" for item in items[:6])


def current_time(_: str = "") -> str:
    return datetime.now(timezone.utc).isoformat()


def sentiment_check(text: str) -> str:
    lower = text.lower()
    positive = sum(word in lower for word in ["good", "great", "success", "completed", "happy", "done", "resolved", "generated"])
    negative = sum(word in lower for word in ["bad", "error", "failed", "angry", "issue", "delay", "risk", "critical", "blocked"])
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def compliance_guard(text: str) -> str:
    blocked = ["password", "api key", "api_key", "secret", "access token", "bearer "]
    matches = [term for term in blocked if term in text.lower()]
    if matches:
        return f"Potential sensitive terms detected: {', '.join(matches)}"
    return "No obvious sensitive credential terms detected."


def pii_redactor(text: str) -> str:
    redacted = re.sub(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL_REDACTED]", text)
    redacted = re.sub(r"\b(?:\+?\d[\d\s-]{8,}\d)\b", "[PHONE_REDACTED]", redacted)
    redacted = re.sub(r"\b\d{12,19}\b", "[LONG_ID_REDACTED]", redacted)
    return redacted


def policy_risk_check(text: str) -> str:
    lower = text.lower()
    risks = []
    if any(k in lower for k in ["password", "token", "secret", "api key"]):
        risks.append("credential_exposure")
    if any(k in lower for k in ["guarantee", "100%", "always", "never fail"]):
        risks.append("overclaiming")
    if any(k in lower for k in ["delete", "drop table", "remove all"]):
        risks.append("destructive_action_review")
    if not risks:
        return "No major policy risks found."
    return "Policy review needed: " + ", ".join(risks)


def schedule_parser(text: str) -> str:
    lower = text.lower()
    if "daily" in lower:
        cadence = "daily"
    elif "weekly" in lower:
        cadence = "weekly"
    elif "tomorrow" in lower:
        cadence = "tomorrow"
    else:
        cadence = "one-time follow-up"
    return f"Schedule recommendation: {cadence}; default checkpoint time: 09:00 local time; reminder owner: workflow requester."


def limit_check(text: str) -> str:
    words = len(text.split())
    severity = "ok" if words <= 800 else "review_needed"
    return f"Input size check: {words} words; status={severity}; max recommended input length=800 words."


def notification_draft(text: str) -> str:
    summary = summarize_text(text, max_sentences=2)
    actions = extract_action_items(text)
    return (
        "WhatsApp-ready stakeholder update:\n"
        f"Status: {summary}\n"
        "Next actions:\n"
        f"{actions}\n"
        "Please confirm once validation is complete."
    )


def memory_note(text: str) -> str:
    return f"Memory note candidate: {summarize_text(text, max_sentences=1)}"


TOOL_REGISTRY: Dict[str, Callable[..., str]] = {
    "calculator": safe_calculator,
    "summarize_text": summarize_text,
    "extract_action_items": extract_action_items,
    "current_time": current_time,
    "sentiment_check": sentiment_check,
    "compliance_guard": compliance_guard,
    "pii_redactor": pii_redactor,
    "policy_risk_check": policy_risk_check,
    "schedule_parser": schedule_parser,
    "limit_check": limit_check,
    "notification_draft": notification_draft,
    "memory_note": memory_note,
    "intent_classifier": intent_classifier,
}


TOOL_DESCRIPTIONS: Dict[str, str] = {
    "calculator": "Safely evaluates basic math expressions.",
    "summarize_text": "Summarizes user input or prior agent output into concise business text.",
    "extract_action_items": "Extracts structured action items for the UI action table.",
    "current_time": "Returns current UTC timestamp.",
    "sentiment_check": "Classifies tone as positive, negative, or neutral.",
    "compliance_guard": "Checks whether text contains credential-like terms.",
    "pii_redactor": "Masks emails, phone numbers, and long numeric identifiers.",
    "policy_risk_check": "Flags credential exposure, overclaiming, and destructive-action risks.",
    "schedule_parser": "Converts schedule/follow-up language into a simple cadence recommendation.",
    "limit_check": "Checks input size against a configured limit.",
    "notification_draft": "Creates a WhatsApp-ready stakeholder notification draft.",
    "memory_note": "Creates a short memory note candidate for future context.",
    "intent_classifier": "Classifies the request into messaging, action planning, incident/risk, summary, or scheduling intent.",
}
