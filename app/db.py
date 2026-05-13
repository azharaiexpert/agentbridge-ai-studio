from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_DB_PATH = os.getenv("AGENTBRIDGE_DB_PATH") or os.getenv("YUNO_DB_PATH", "./data/agentbridge_ai.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def conn(self):
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self.conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    model TEXT NOT NULL,
                    tools TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    schedules TEXT NOT NULL,
                    memory_enabled INTEGER NOT NULL,
                    skills TEXT NOT NULL,
                    interaction_rules TEXT NOT NULL,
                    guardrails TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    nodes TEXT NOT NULL,
                    edges TEXT NOT NULL,
                    entry_node TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    sender_type TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    conversation_id TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(agent_id, key)
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    workflow_id INTEGER,
                    tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS integration_settings (
                    channel TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    is_secret INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(channel, key)
                );
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _loads(value: str) -> Any:
        return json.loads(value) if value else None

    def create_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utc_now()
        with self.conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO agents(name, role, system_prompt, model, tools, channels, schedules,
                                   memory_enabled, skills, interaction_rules, guardrails, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"], payload["role"], payload["system_prompt"], payload["model"],
                    self._json(payload.get("tools", [])), self._json(payload.get("channels", [])),
                    self._json(payload.get("schedules", [])), int(payload.get("memory_enabled", True)),
                    self._json(payload.get("skills", [])), self._json(payload.get("interaction_rules", [])),
                    self._json(payload.get("guardrails", {})), now, now,
                ),
            )
            agent_id = cur.lastrowid
        return self.get_agent(agent_id)

    def update_agent(self, agent_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_agent(agent_id)
        if not existing:
            return None
        merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
        now = utc_now()
        with self.conn() as conn:
            conn.execute(
                """
                UPDATE agents SET name=?, role=?, system_prompt=?, model=?, tools=?, channels=?, schedules=?,
                    memory_enabled=?, skills=?, interaction_rules=?, guardrails=?, updated_at=? WHERE id=?
                """,
                (
                    merged["name"], merged["role"], merged["system_prompt"], merged["model"],
                    self._json(merged.get("tools", [])), self._json(merged.get("channels", [])),
                    self._json(merged.get("schedules", [])), int(merged.get("memory_enabled", True)),
                    self._json(merged.get("skills", [])), self._json(merged.get("interaction_rules", [])),
                    self._json(merged.get("guardrails", {})), now, agent_id,
                ),
            )
            return self.get_agent(agent_id)

    def delete_agent(self, agent_id: int) -> bool:
        with self.conn() as conn:
            cur = conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
            return cur.rowcount > 0

    def get_agent(self, agent_id: int) -> Optional[Dict[str, Any]]:
        with self.conn() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
            return self._agent_from_row(row) if row else None

    def list_agents(self) -> List[Dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
            return [self._agent_from_row(row) for row in rows]

    def _agent_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in ["tools", "channels", "schedules", "skills", "interaction_rules", "guardrails"]:
            data[key] = self._loads(data[key])
        data["memory_enabled"] = bool(data["memory_enabled"])
        return data

    def create_workflow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utc_now()
        with self.conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO workflows(name, description, nodes, edges, entry_node, max_steps, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"], payload.get("description", ""), self._json(payload["nodes"]),
                    self._json(payload["edges"]), payload["entry_node"], int(payload.get("max_steps", 8)), now, now,
                ),
            )
            workflow_id = cur.lastrowid
        return self.get_workflow(workflow_id)

    def update_workflow(self, workflow_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_workflow(workflow_id)
        if not existing:
            return None
        merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
        now = utc_now()
        with self.conn() as conn:
            conn.execute(
                """
                UPDATE workflows SET name=?, description=?, nodes=?, edges=?, entry_node=?, max_steps=?, updated_at=?
                WHERE id=?
                """,
                (
                    merged["name"], merged.get("description", ""), self._json(merged["nodes"]),
                    self._json(merged["edges"]), merged["entry_node"], int(merged.get("max_steps", 8)), now, workflow_id,
                ),
            )
            return self.get_workflow(workflow_id)

    def delete_workflow(self, workflow_id: int) -> bool:
        with self.conn() as conn:
            cur = conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
            return cur.rowcount > 0

    def get_workflow(self, workflow_id: int) -> Optional[Dict[str, Any]]:
        with self.conn() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            return self._workflow_from_row(row) if row else None

    def list_workflows(self) -> List[Dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM workflows ORDER BY id").fetchall()
            return [self._workflow_from_row(row) for row in rows]

    def _workflow_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["nodes"] = self._loads(data["nodes"])
        data["edges"] = self._loads(data["edges"])
        return data

    def add_message(self, conversation_id: str, sender_type: str, sender_id: str, channel: str,
                    content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = utc_now()
        with self.conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages(conversation_id, sender_type, sender_id, channel, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, sender_type, sender_id, channel, content, self._json(metadata or {}), now),
            )
            message_id = cur.lastrowid
        return self.get_message(message_id)

    def get_message(self, message_id: int) -> Dict[str, Any]:
        with self.conn() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            data = dict(row)
            data["metadata"] = self._loads(data["metadata"])
            return data

    def list_messages(self, conversation_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self.conn() as conn:
            if conversation_id:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE conversation_id=? ORDER BY id LIMIT ?",
                    (conversation_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for row in rows:
                data = dict(row)
                data["metadata"] = self._loads(data["metadata"])
                out.append(data)
            return out

    def add_log(self, level: str, event_type: str, message: str, conversation_id: Optional[str] = None,
                metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = utc_now()
        with self.conn() as conn:
            cur = conn.execute(
                "INSERT INTO logs(level, event_type, message, conversation_id, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (level, event_type, message, conversation_id, self._json(metadata or {}), now),
            )
            log_id = cur.lastrowid
        return self.get_log(log_id)

    def get_log(self, log_id: int) -> Dict[str, Any]:
        with self.conn() as conn:
            row = conn.execute("SELECT * FROM logs WHERE id=?", (log_id,)).fetchone()
            data = dict(row)
            data["metadata"] = self._loads(data["metadata"])
            return data

    def list_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self.conn() as conn:
            rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for row in rows:
                data = dict(row)
                data["metadata"] = self._loads(data["metadata"])
                out.append(data)
            return out

    def upsert_memory(self, agent_id: int, key: str, value: str) -> None:
        now = utc_now()
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO memory(agent_id, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (agent_id, key, value, now, now),
            )

    def get_memory(self, agent_id: int) -> Dict[str, str]:
        with self.conn() as conn:
            rows = conn.execute("SELECT key, value FROM memory WHERE agent_id=? ORDER BY key", (agent_id,)).fetchall()
            return {row["key"]: row["value"] for row in rows}

    def add_metrics(self, conversation_id: str, workflow_id: Optional[int], tokens: int,
                    estimated_cost_usd: float, latency_ms: int) -> None:
        with self.conn() as conn:
            conn.execute(
                "INSERT INTO metrics(conversation_id, workflow_id, tokens, estimated_cost_usd, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, workflow_id, tokens, estimated_cost_usd, latency_ms, utc_now()),
            )

    def metrics_summary(self) -> Dict[str, Any]:
        with self.conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS runs, COALESCE(SUM(tokens),0) AS tokens, COALESCE(SUM(estimated_cost_usd),0) AS cost, COALESCE(AVG(latency_ms),0) AS avg_latency FROM metrics"
            ).fetchone()
            return dict(row)

    def upsert_integration_settings(self, channel: str, settings: Dict[str, Any], secret_keys: Optional[Iterable[str]] = None) -> None:
        now = utc_now()
        secret_key_set = set(secret_keys or [])
        with self.conn() as conn:
            for key, value in settings.items():
                if value is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO integration_settings(channel, key, value, is_secret, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel, key) DO UPDATE SET
                        value=excluded.value,
                        is_secret=excluded.is_secret,
                        updated_at=excluded.updated_at
                    """,
                    (channel, key, str(value), int(key in secret_key_set), now, now),
                )

    def get_integration_settings(self, channel: str, reveal_secrets: bool = False) -> Dict[str, Any]:
        with self.conn() as conn:
            rows = conn.execute(
                "SELECT key, value, is_secret FROM integration_settings WHERE channel=? ORDER BY key",
                (channel,),
            ).fetchall()
            settings: Dict[str, Any] = {}
            for row in rows:
                if row["is_secret"] and not reveal_secrets:
                    settings[row["key"]] = "********" if row["value"] else ""
                else:
                    settings[row["key"]] = row["value"]
            return settings

    def get_integration_secret(self, channel: str, key: str) -> Optional[str]:
        with self.conn() as conn:
            row = conn.execute(
                "SELECT value FROM integration_settings WHERE channel=? AND key=?",
                (channel, key),
            ).fetchone()
            return row["value"] if row else None
