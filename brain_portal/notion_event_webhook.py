from __future__ import annotations

import hashlib
import hmac

from flask import Blueprint, abort, request

from brain_portal.notion_jobs import enqueue_notion_event


SIGNAL_EVENT_TYPES = {"page.content_updated", "page.properties_updated"}


def create_tenant_aware_notion_webhook_blueprint(repository, *, webhook_secret: str) -> Blueprint:
    webhook = Blueprint("tenant_aware_notion_webhook", __name__)

    @webhook.post("/hooks/notion/events")
    def receive():
        raw_body = request.get_data()
        signature = request.headers.get("X-Notion-Signature", "")
        if not _valid_signature(webhook_secret, raw_body, signature):
            abort(401)
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        entity = payload.get("entity")
        page_id = entity.get("id") if isinstance(entity, dict) else ""
        event_type = payload.get("type")
        if (
            isinstance(event_type, str)
            and event_type in SIGNAL_EVENT_TYPES
            and isinstance(payload.get("id"), str)
            and isinstance(payload.get("workspace_id"), str)
            and isinstance(page_id, str)
        ):
            enqueue_notion_event(
                repository,
                event_id=payload["id"],
                workspace_id=payload["workspace_id"],
                event_type=event_type,
                page_id=page_id,
            )
        return ("", 202)

    return webhook


def _valid_signature(secret: str, raw_body: bytes, signature_header: str) -> bool:
    if not secret.strip() or not signature_header.strip():
        return False
    provided = signature_header.removeprefix("sha256=")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
