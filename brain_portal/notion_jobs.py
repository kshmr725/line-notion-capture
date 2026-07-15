from __future__ import annotations

import json
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from brain_portal.auth import decrypt_source_token
from brain_portal.config import PortalSettings
from brain_portal.connectors.notion import NotionConnector
from brain_portal.db import PortalRepository, portal_connect
from brain_portal.indexer import index_document, record_permission_denied
from flask import Blueprint, abort, jsonify, request


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
    job = _claim_next_job(repository, lease_seconds=settings.queue_lease_seconds)
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
        return _retry_or_finish(
            repository,
            event_id,
            "processing_failed",
            max_attempts=max(1, settings.queue_max_attempts),
        )


def _claim_next_job(
    repository: PortalRepository, *, lease_seconds: int = 300
) -> tuple[str, str, str] | None:
    now = datetime.now(timezone.utc)
    now_text = now.isoformat().replace("+00:00", "Z")
    lease_expires = (now + timedelta(seconds=max(30, lease_seconds))).isoformat().replace(
        "+00:00", "Z"
    )
    lease_owner = uuid.uuid4().hex
    connection = portal_connect(repository.path)
    try:
        with connection:
            row = connection.execute(
                """
                SELECT event_id, tenant_id, page_id FROM notion_sync_jobs
                WHERE (
                    status = 'queued' AND (available_at IS NULL OR available_at <= ?)
                ) OR (
                    status = 'processing' AND lease_expires_at IS NOT NULL
                    AND lease_expires_at <= ?
                )
                ORDER BY created_at LIMIT 1
                """,
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE notion_sync_jobs
                SET status = 'processing', started_at = ?,
                    lease_owner = ?, lease_expires_at = ?
                WHERE event_id = ? AND (
                    (status = 'queued' AND (available_at IS NULL OR available_at <= ?))
                    OR (status = 'processing' AND lease_expires_at IS NOT NULL
                        AND lease_expires_at <= ?)
                )
                """,
                (
                    now_text,
                    lease_owner,
                    lease_expires,
                    row["event_id"],
                    now_text,
                    now_text,
                ),
            )
            if updated.rowcount != 1:
                return None
            return row["event_id"], row["tenant_id"], row["page_id"]
    finally:
        connection.close()


def create_queue_processor_blueprint(
    *, processor_token: str, process_one, batch_limit: int = 10
) -> Blueprint:
    blueprint = Blueprint("notion_queue_processor", __name__)

    @blueprint.post("/internal/process-notion-jobs")
    def process_jobs():
        provided = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not processor_token.strip() or not hmac.compare_digest(
            provided.encode("utf-8"), processor_token.encode("utf-8")
        ):
            abort(401)
        processed = 0
        for _ in range(max(1, min(batch_limit, 50))):
            status = process_one()
            if status is None:
                break
            processed += 1
        return jsonify({"processed": processed})

    return blueprint


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
                    finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    lease_owner = NULL, lease_expires_at = NULL
                WHERE event_id = ?
                """,
                (status, error_code, event_id),
            )
    finally:
        connection.close()


def _retry_or_finish(
    repository: PortalRepository,
    event_id: str,
    error_code: str,
    *,
    max_attempts: int,
) -> str:
    connection = portal_connect(repository.path)
    try:
        with connection:
            row = connection.execute(
                "SELECT attempt_count FROM notion_sync_jobs WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            attempts = (int(row["attempt_count"]) if row is not None else 0) + 1
            terminal = attempts >= max_attempts
            available_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=min(300, 2 ** min(attempts, 8)))
            ).isoformat().replace("+00:00", "Z")
            connection.execute(
                """
                UPDATE notion_sync_jobs
                SET status = ?, attempt_count = ?, error_code = ?, available_at = ?,
                    started_at = NULL, lease_owner = NULL, lease_expires_at = NULL,
                    finished_at = CASE WHEN ? THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') ELSE NULL END
                WHERE event_id = ?
                """,
                (
                    "dead_letter" if terminal else "queued",
                    attempts,
                    error_code,
                    None if terminal else available_at,
                    terminal,
                    event_id,
                ),
            )
            return "failed" if terminal else "retrying"
    finally:
        connection.close()
