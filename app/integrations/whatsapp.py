from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.db import Database


SECRET_KEYS = {"access_token", "app_secret", "verify_token"}


@dataclass
class WhatsAppSettings:
    access_token: str = ""
    phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    verify_token: str = ""
    app_secret: str = ""
    graph_api_version: str = "v21.0"
    test_recipient_number: str = ""
    auto_reply_enabled: bool = True
    default_workflow_id: Optional[int] = None

    @property
    def is_ready_to_send(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    @property
    def is_ready_for_webhook_verification(self) -> bool:
        return bool(self.verify_token)


def _bool_value(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_whatsapp_number(value: str) -> str:
    """Return WhatsApp number in E.164 digits-only form, e.g. 919876543210."""
    return re.sub(r"\D+", "", value or "")


def load_whatsapp_settings(db: Database, reveal_secrets: bool = True) -> WhatsAppSettings:
    db_settings = db.get_integration_settings("whatsapp", reveal_secrets=reveal_secrets)
    env_settings = {
        "access_token": os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
        "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        "whatsapp_business_account_id": os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
        "verify_token": os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
        "app_secret": os.getenv("WHATSAPP_APP_SECRET", ""),
        "graph_api_version": os.getenv("WHATSAPP_GRAPH_API_VERSION", "v21.0"),
        "test_recipient_number": os.getenv("WHATSAPP_TEST_RECIPIENT_NUMBER", ""),
        "auto_reply_enabled": os.getenv("WHATSAPP_AUTO_REPLY_ENABLED", "true"),
        "default_workflow_id": os.getenv("WHATSAPP_DEFAULT_WORKFLOW_ID", ""),
    }
    merged: Dict[str, Any] = {**env_settings, **{k: v for k, v in db_settings.items() if v not in (None, "")}}
    return WhatsAppSettings(
        access_token=str(merged.get("access_token") or ""),
        phone_number_id=str(merged.get("phone_number_id") or ""),
        whatsapp_business_account_id=str(merged.get("whatsapp_business_account_id") or ""),
        verify_token=str(merged.get("verify_token") or ""),
        app_secret=str(merged.get("app_secret") or ""),
        graph_api_version=str(merged.get("graph_api_version") or "v21.0"),
        test_recipient_number=normalize_whatsapp_number(str(merged.get("test_recipient_number") or "")),
        auto_reply_enabled=_bool_value(merged.get("auto_reply_enabled"), default=True),
        default_workflow_id=_int_or_none(merged.get("default_workflow_id")),
    )


def save_whatsapp_settings(db: Database, payload: Dict[str, Any]) -> None:
    current = db.get_integration_settings("whatsapp", reveal_secrets=True)
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in SECRET_KEYS and value in (None, "", "********"):
            # Preserve existing secret if the user leaves a secret blank or masked in the UI.
            if current.get(key):
                continue
        if value is None:
            value = ""
        if key == "test_recipient_number":
            value = normalize_whatsapp_number(str(value))
        clean[key] = value
    if clean:
        db.upsert_integration_settings("whatsapp", clean, secret_keys=SECRET_KEYS)


def safe_public_config(settings: WhatsAppSettings) -> Dict[str, Any]:
    return {
        "access_token": "********" if settings.access_token else "",
        "phone_number_id": settings.phone_number_id,
        "whatsapp_business_account_id": settings.whatsapp_business_account_id,
        "verify_token": "********" if settings.verify_token else "",
        "app_secret": "********" if settings.app_secret else "",
        "graph_api_version": settings.graph_api_version,
        "test_recipient_number": settings.test_recipient_number,
        "auto_reply_enabled": settings.auto_reply_enabled,
        "default_workflow_id": settings.default_workflow_id,
        "is_ready_to_send": settings.is_ready_to_send,
        "is_ready_for_webhook_verification": settings.is_ready_for_webhook_verification,
    }


class WhatsAppCloudClient:
    def __init__(self, settings: WhatsAppSettings):
        self.settings = settings

    def _endpoint(self) -> str:
        version = self.settings.graph_api_version.strip().lstrip("/") or "v21.0"
        return f"https://graph.facebook.com/{version}/{self.settings.phone_number_id}/messages"

    async def send_text(self, to: str, text: str, preview_url: bool = False) -> Dict[str, Any]:
        to = normalize_whatsapp_number(to)
        if not to:
            raise ValueError("Missing WhatsApp recipient number")
        if not self.settings.is_ready_to_send:
            missing = []
            if not self.settings.access_token:
                missing.append("WHATSAPP_ACCESS_TOKEN")
            if not self.settings.phone_number_id:
                missing.append("WHATSAPP_PHONE_NUMBER_ID")
            raise ValueError("Missing WhatsApp configuration: " + ", ".join(missing))
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text[:4096], "preview_url": preview_url},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(self._endpoint(), headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def send_hello_world_template(self, to: str) -> Dict[str, Any]:
        """Send Meta's standard hello_world test template. Useful before a 24-hour session exists."""
        to = normalize_whatsapp_number(to)
        if not self.settings.is_ready_to_send:
            raise ValueError("Missing WhatsApp configuration: WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID")
        if not to:
            raise ValueError("Missing WhatsApp recipient number")
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": "hello_world", "language": {"code": "en_US"}},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(self._endpoint(), headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def verify_signature(self, body: bytes, signature_header: Optional[str]) -> bool:
        if not self.settings.app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            self.settings.app_secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)


def extract_whatsapp_messages(update: Dict[str, Any]) -> List[Dict[str, str]]:
    parsed: List[Dict[str, str]] = []
    for entry in update.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                msg_type = msg.get("type")
                sender = str(msg.get("from", "whatsapp-user"))
                message_id = str(msg.get("id", ""))
                if msg_type == "text":
                    text = (msg.get("text") or {}).get("body", "")
                elif msg_type == "button":
                    text = (msg.get("button") or {}).get("text", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive") or {}
                    text = (
                        (interactive.get("button_reply") or {}).get("title")
                        or (interactive.get("list_reply") or {}).get("title")
                        or "Received interactive WhatsApp message"
                    )
                else:
                    text = f"Received unsupported WhatsApp message type: {msg_type}"
                if text:
                    parsed.append({"from": sender, "text": text, "message_id": message_id, "type": str(msg_type or "unknown")})
    return parsed
