from __future__ import annotations

import json

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
import brain_portal.notion_jobs as notion_jobs


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
