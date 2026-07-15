from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.models import SourceDocument
import brain_portal.notion_jobs as notion_jobs
from scripts import process_notion_sync_jobs


def _repository(tmp_path) -> PortalRepository:
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    connection = portal_connect(path)
    with connection:
        for tenant_id, workspace_id in (("tenant-a", "workspace-a"), ("tenant-b", "workspace-b")):
            connection.execute(
                "INSERT INTO tenants (tenant_id, display_name) VALUES (?, ?)",
                (tenant_id, tenant_id),
            )
            connection.execute(
                """
                INSERT INTO source_connections
                    (tenant_id, source_type, connection_id, config_json, status)
                VALUES (?, 'notion', ?, ?, 'active')
                """,
                (tenant_id, workspace_id, json.dumps({"workspace_id": workspace_id})),
            )
    connection.close()
    return PortalRepository(path)


def test_enqueue_notion_event_resolves_tenant_only_from_server_connection(tmp_path):
    repository = _repository(tmp_path)

    queued = notion_jobs.enqueue_notion_event(
        repository,
        event_id="event-1",
        workspace_id="workspace-b",
        event_type="page.content_updated",
        page_id="page-1",
    )

    connection = portal_connect(repository.path)
    jobs = connection.execute(
        "SELECT tenant_id, event_id, page_id, status FROM notion_sync_jobs"
    ).fetchall()
    connection.close()
    assert queued is True
    assert [tuple(row) for row in jobs] == [("tenant-b", "event-1", "page-1", "queued")]


def test_enqueue_notion_event_is_idempotent_and_ignores_unknown_workspace(tmp_path):
    repository = _repository(tmp_path)
    event = {
        "event_id": "event-1",
        "workspace_id": "workspace-a",
        "event_type": "page.properties_updated",
        "page_id": "page-1",
    }

    assert notion_jobs.enqueue_notion_event(repository, **event) is True
    assert notion_jobs.enqueue_notion_event(repository, **event) is False
    assert notion_jobs.enqueue_notion_event(
        repository,
        event_id="event-unknown",
        workspace_id="workspace-unknown",
        event_type="page.content_updated",
        page_id="page-2",
    ) is False

    connection = portal_connect(repository.path)
    assert connection.execute("SELECT COUNT(*) FROM notion_webhook_events").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM notion_sync_jobs").fetchone()[0] == 1
    connection.close()


def test_processor_claims_one_job_and_indexes_only_the_resolved_tenant(tmp_path):
    repository = _repository(tmp_path)
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "UPDATE source_connections SET config_json = ? WHERE tenant_id = 'tenant-a'",
            (json.dumps({"workspace_id": "workspace-a", "database_id": "db-a", "token_ciphertext": "ignored"}),),
        )
    connection.close()
    notion_jobs.enqueue_notion_event(
        repository, event_id="event-1", workspace_id="workspace-a", event_type="page.content_updated", page_id="page-1"
    )
    calls = []

    class Connector:
        def fetch_document(self, tenant_id, page_id):
            calls.append((tenant_id, page_id))
            return SourceDocument(
                tenant_id=tenant_id, source_id=page_id, source_type="notion",
                canonical_ref="https://www.notion.so/page-1", title="Queued page", body="Body",
                cloud_key="ai", source_revision="rev-1", updated_at="2026-07-15T00:00:00Z", metadata={},
            )

    status = notion_jobs.process_next_notion_job(
        PortalSettings(token_encryption_key="test-key"), repository, None,
        connector_factory=lambda **kwargs: Connector(), decryptor=lambda settings, config: "token-a",
    )

    assert status == "completed"
    assert calls == [("tenant-a", "page-1")]
    assert repository.get_item("tenant-a", "page-1") is not None
    assert repository.get_item("tenant-b", "page-1") is None


def test_processor_returns_none_when_queue_is_empty(tmp_path):
    repository = _repository(tmp_path)

    assert notion_jobs.process_next_notion_job(
        PortalSettings(), repository, None, decryptor=lambda settings, config: "unused"
    ) is None


def test_processor_command_processes_at_most_one_job(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        process_notion_sync_jobs,
        "PortalSettings",
        lambda: SimpleNamespace(database_path=str(tmp_path / "portal.sqlite3"), gemini_api_key="", ai_timeout_seconds=20),
    )
    monkeypatch.setattr(process_notion_sync_jobs, "PortalRepository", lambda path: "repo")
    monkeypatch.setattr(process_notion_sync_jobs, "process_next_notion_job", lambda *args: "completed")

    assert process_notion_sync_jobs.main() == 0
    assert capsys.readouterr().out.strip() == "completed"


def test_processor_script_runs_from_the_repository_root(tmp_path):
    database = tmp_path / "portal.sqlite3"
    environment = {**os.environ, "PORTAL_DATABASE_PATH": str(database), "GEMINI_API_KEY": ""}

    result = subprocess.run(
        [sys.executable, "scripts/process_notion_sync_jobs.py"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "idle"
