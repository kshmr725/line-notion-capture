from __future__ import annotations

import json

from brain_portal.db import PortalRepository, portal_connect


def enqueue_notion_event(
    repository: PortalRepository,
    *,
    event_id: str,
    workspace_id: str,
    event_type: str,
    page_id: str,
) -> bool:
    """Atomically queue one trusted Notion event without accepting a tenant id."""
    values = (event_id.strip(), workspace_id.strip(), event_type.strip(), page_id.strip())
    if not all(values):
        return False
    event_id, workspace_id, event_type, page_id = values
    connection = portal_connect(repository.path)
    try:
        with connection:
            rows = connection.execute(
                """
                SELECT tenant_id, config_json FROM source_connections
                WHERE source_type = 'notion' AND status = 'active'
                """
            ).fetchall()
            tenant_id = next(
                (
                    row["tenant_id"]
                    for row in rows
                    if _workspace_id(row["config_json"]) == workspace_id
                ),
                None,
            )
            if tenant_id is None:
                return False
            inserted = connection.execute(
                """
                INSERT INTO notion_webhook_events
                    (event_id, tenant_id, workspace_id, event_type, page_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (event_id, tenant_id, workspace_id, event_type, page_id),
            )
            if inserted.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO notion_sync_jobs (event_id, tenant_id, page_id, status)
                VALUES (?, ?, ?, 'queued')
                """,
                (event_id, tenant_id, page_id),
            )
            return True
    finally:
        connection.close()


def _workspace_id(config_json: str) -> str:
    try:
        config = json.loads(config_json)
    except (TypeError, json.JSONDecodeError):
        return ""
    return str(config.get("workspace_id") or "").strip()
