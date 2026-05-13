from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from app.db import Database
from app.models import RunResult
from app.runtime.agents import AgentRuntime
from app.runtime.tools import estimate_tokens, extract_action_items, sentiment_check, compliance_guard


class WorkflowRuntime:
    def __init__(self, db: Database, agent_runtime: AgentRuntime):
        self.db = db
        self.agent_runtime = agent_runtime

    def _node_by_id(self, workflow: Dict[str, Any], node_id: str) -> Dict[str, Any]:
        for node in workflow["nodes"]:
            if node["id"] == node_id:
                return node
        raise ValueError(f"Node {node_id} not found")

    def _outgoing_edges(self, workflow: Dict[str, Any], node_id: str) -> List[Dict[str, Any]]:
        return [edge for edge in workflow["edges"] if edge["source"] == node_id]

    def _condition_matches(self, condition: str, latest_answer: str, user_input: str) -> bool:
        condition = (condition or "always").strip().lower()
        haystack = f"{latest_answer}\n{user_input}".lower()
        if condition == "always":
            return True
        if condition.startswith("contains:"):
            needle = condition.split(":", 1)[1].strip()
            return needle in haystack
        if condition == "if_negative_sentiment":
            # Feedback loops should be driven by reviewer output, not by the original user text.
            # Otherwise every incident prompt containing words like failed/delay loops unnecessarily.
            latest = (latest_answer or "").lower()
            return any(w in latest for w in ["needs revision", "not ready", "incomplete", "unsafe", "failed review", "revise"])
        if condition == "if_summary_needed":
            return any(w in user_input.lower() for w in ["summary", "summarize", "brief", "explain", "report", "update"])
        if condition == "if_whatsapp_requested":
            return any(w in user_input.lower() for w in ["whatsapp", "notify", "message", "send"])
        return False

    @staticmethod
    def _parse_action_items(text: str) -> List[str]:
        items: List[str] = []
        for line in (text or "").splitlines():
            clean = line.strip()
            if clean.startswith(("- ", "• ", "* ")):
                clean = clean[2:].strip()
            elif len(clean) > 2 and clean[0].isdigit() and clean[1] in {".", ")"}:
                clean = clean[2:].strip()
            else:
                continue
            if clean and clean not in items:
                items.append(clean)
        return items

    def _collect_action_items(self, user_input: str, steps: List[Dict[str, Any]]) -> List[str]:
        items: List[str] = []
        for step in steps:
            for trace in step.get("tool_trace", []) or []:
                if trace.get("tool") == "extract_action_items" and trace.get("output"):
                    for item in self._parse_action_items(trace["output"]):
                        if item not in items:
                            items.append(item)
            # Also scan LLM answer in case the LLM created new action bullets.
            for item in self._parse_action_items(step.get("answer", "")):
                if item not in items:
                    items.append(item)
        if not items:
            items = self._parse_action_items(extract_action_items(user_input))
        return items[:8]

    async def run_workflow(self, workflow_id: int, user_input: str, channel: str = "web",
                           conversation_id: Optional[str] = None) -> RunResult:
        workflow = self.db.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        conversation_id = conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        start = time.perf_counter()
        self.db.add_message(conversation_id, "human", "user", channel, user_input, {"workflow_id": workflow_id})
        self.db.add_log("INFO", "workflow_started", f"Workflow '{workflow['name']}' started", conversation_id, {"workflow_id": workflow_id})

        current_node_id = workflow["entry_node"]
        steps: List[Dict[str, Any]] = []
        latest_payload = user_input
        final_answer = ""
        total_tokens = 0
        visited_loop_count: Dict[str, int] = {}

        for step_idx in range(workflow.get("max_steps", 8)):
            node = self._node_by_id(workflow, current_node_id)
            agent_id = int(node["agent_id"])
            output = await self.agent_runtime.run_agent(
                agent_id,
                latest_payload,
                conversation_id,
                channel="agent-bus" if channel != "local-messenger" else channel,
                workflow_context={"workflow": workflow["name"], "node": node["label"], "step": step_idx + 1},
            )
            total_tokens += output.tokens
            final_answer = output.answer
            step_record = {
                "step": step_idx + 1,
                "node_id": current_node_id,
                "node_label": node["label"],
                "agent_id": agent_id,
                "answer": output.answer,
                "tool_trace": output.tool_trace,
            }
            steps.append(step_record)

            outgoing = self._outgoing_edges(workflow, current_node_id)
            if not outgoing:
                break

            matched_edge = None
            for edge in outgoing:
                loop_key = f"{edge['source']}->{edge['target']}"
                if edge.get("feedback_loop"):
                    visited_loop_count[loop_key] = visited_loop_count.get(loop_key, 0) + 1
                    if visited_loop_count[loop_key] > 1:
                        continue
                if self._condition_matches(edge.get("condition", "always"), output.answer, user_input):
                    matched_edge = edge
                    break
            if not matched_edge:
                break

            target = self._node_by_id(workflow, matched_edge["target"])
            await self.agent_runtime.send_async_message(
                conversation_id=conversation_id,
                source_agent_id=agent_id,
                target_agent_id=int(target["agent_id"]),
                content=output.answer,
            )
            latest_payload = f"Original user task: {user_input}\nPrevious agent output: {output.answer}"
            current_node_id = matched_edge["target"]

        action_items = self._collect_action_items(user_input, steps)
        sentiment = sentiment_check(f"{user_input}\n{final_answer}")
        compliance_status = compliance_guard(f"{user_input}\n{final_answer}")
        latency_ms = int((time.perf_counter() - start) * 1000)
        total_tokens = max(total_tokens, estimate_tokens(user_input + final_answer))
        estimated_cost = 0.0

        metadata = {
            "steps": steps,
            "action_items": action_items,
            "sentiment": sentiment,
            "compliance_status": compliance_status,
        }
        self.db.add_message(conversation_id, "workflow", str(workflow_id), channel, final_answer, metadata)
        self.db.add_metrics(conversation_id, workflow_id, total_tokens, estimated_cost, latency_ms)
        self.db.add_log(
            "INFO",
            "workflow_completed",
            f"Workflow '{workflow['name']}' completed with {len(action_items)} action item(s)",
            conversation_id,
            {"latency_ms": latency_ms, "tokens": total_tokens, "action_items": action_items},
        )

        return RunResult(
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            final_answer=final_answer,
            steps=steps,
            tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
            action_items=action_items,
            sentiment=sentiment,
            compliance_status=compliance_status,
        )
