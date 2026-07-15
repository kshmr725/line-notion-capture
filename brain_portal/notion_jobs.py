from __future__ import annotations

import json

from brain_portal.auth import decrypt_source_token
from brain_portal.config import PortalSettings
from brain_portal.connectors.notion import NotionConnector
from brain_portal.db import PortalRepository, portal_connect
from brain_portal.indexer import index_document, record_permission_denied


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


def process_next_notion_job(
    settings: PortalSettings,
    repository: PortalRepository,
    embedder,
    *,
    connector_factory=NotionConnector,
    decryptor=decrypt_source_token,
) -> str | None:
    """Claim at most one queued event and update only its resolved tenant."""
    job = _claim_next_job(repository)
    if job is None:
        return None
    event_id, tenant_id, page_id = job
    config = _connection_config(repository, tenant_id)
    if config is None or not str(config.get("database_id") or "").strip():
        _finish_job(repository, event_id, "failed", "missing_connection")
        return "failed"
    try:
        token = decryptor(settings, config)
        connector = connector_factory(
            token=token,
            database_id=str(config["database_id"]),
            api_version=settings.notion_api_version,
        )
        document = connector.fetch_document(tenant_id, page_id)
        report = index_document(tenant_id, document, repository, embedder)
        status = "completed" if report.failed == 0 else "failed"
        _finish_job(repository, event_id, status, None if status == "completed" else "index_failed")
        return status
    except PermissionError as error:
        record_permission_denied(tenant_id, "notion", repository, str(error))
        _finish_job(repository, event_id, "failed", "permission_required")
        return "failed"
    except Exception:
        _finish_job(repository, event_id, "failed", "processing_failed")
        return "failed"


def _claim_next_job(repository: PortalRepository) -> tuple[str, str, str] | None:
    connection = portal_connect(repository.path)
    try:
        with connection:
            row = connection.execute(
                """
                SELECT event_id, tenant_id, page_id FROM notion_sync_jobs
                WHERE status = 'queued' ORDER BY created_at LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE notion_sync_jobs
                SET status = 'processing', started_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE event_id = ? AND status = 'queued'
                """,
                (row["event_id"],),
            )
            if updated.rowcount != 1:
                return None
            return row["event_id"], row["tenant_id"], row["page_id"]
    finally:
        connection.close()


def _connection_config(repository: PortalRepository, tenant_id: str) -> dict | None:
    connection = portal_connect(repository.path)
    try:
        row = connection.execute(
            """
            SELECT config_json FROM source_connections
            WHERE tenant_id = ? AND source_type = 'notion' AND status = 'active'
            ORDER BY connection_id LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        config = json.loads(row["config_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


def _finish_job(repository: PortalRepository, event_id: str, status: str, error_code: str | None) -> None:
    connection = portal_connect(repository.path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE notion_sync_jobs
                SET status = ?, error_code = ?,
                    finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE event_id = ?
                """,
                (status, error_code, event_id),
            )
    finally:
        connection.close()
