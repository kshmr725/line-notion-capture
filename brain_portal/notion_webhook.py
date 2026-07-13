from __future__ import annotations

import hashlib
import hmac

from flask import Blueprint, Response, abort, request

from brain_portal.indexer import index_document


SIGNAL_EVENT_TYPES = {"page.content_updated", "page.properties_updated"}


def create_notion_webhook_blueprint(
    *,
    tenant_id: str,
    connector,
    repo,
    embedder,
    webhook_secret: str,
) -> Blueprint:
    webhook = Blueprint("notion_webhook", __name__)

    @webhook.post("/hooks/notion")
    def receive() -> Response:
        raw_body = request.get_data()
        signature = request.headers.get("X-Notion-Signature", "")
        if not _valid_signature(webhook_secret, raw_body, signature):
            abort(401)
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        event_type = payload.get("type")
        entity = payload.get("entity")
        page_id = entity.get("id") if isinstance(entity, dict) else None
        if event_type in SIGNAL_EVENT_TYPES and isinstance(page_id, str) and page_id.strip():
            document = connector.fetch_document(tenant_id, page_id)
            index_document(tenant_id, document, repo, embedder)
        return ("", 202)

    return webhook


def _valid_signature(secret: str, raw_body: bytes, signature_header: str) -> bool:
    if not secret.strip() or not signature_header.strip():
        return False
    prefix = "sha256="
    provided = (
        signature_header[len(prefix):]
        if signature_header.startswith(prefix)
        else signature_header
    )
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
