from __future__ import annotations

import hashlib
import hmac
import json

from flask import Flask

import portal_app
from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db, portal_connect
import brain_portal.notion_event_webhook as event_webhook


def _client(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repository = PortalRepository(path)
    connection = portal_connect(path)
    with connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, display_name) VALUES ('tenant-a', 'Tenant A')"
        )
        connection.execute(
            """
            INSERT INTO source_connections
                (tenant_id, source_type, connection_id, config_json, status)
            VALUES ('tenant-a', 'notion', 'workspace-a', '{"workspace_id":"workspace-a"}', 'active')
            """
        )
    connection.close()
    app = Flask(__name__)
    app.register_blueprint(
        event_webhook.create_tenant_aware_notion_webhook_blueprint(
            repository, webhook_secret="shhh"
        )
    )
    app.config.update(TESTING=True)
    return app.test_client(), repository


def _post(client, payload, signature=None):
    body = json.dumps(payload).encode()
    signature = signature or "sha256=" + hmac.new(b"shhh", body, hashlib.sha256).hexdigest()
    return client.post(
        "/hooks/notion/events",
        data=body,
        content_type="application/json",
        headers={"X-Notion-Signature": signature},
    )


def test_signed_webhook_queues_only_the_resolved_workspace_tenant(tmp_path):
    client, repository = _client(tmp_path)

    response = _post(
        client,
        {
            "id": "event-1",
            "workspace_id": "workspace-a",
            "type": "page.content_updated",
            "entity": {"id": "page-1"},
            "tenant_id": "attacker",
        },
    )

    assert response.status_code == 202
    connection = portal_connect(repository.path)
    job = connection.execute("SELECT tenant_id, page_id FROM notion_sync_jobs").fetchone()
    connection.close()
    assert tuple(job) == ("tenant-a", "page-1")


def test_invalid_signature_is_rejected_before_any_job_is_queued(tmp_path):
    client, repository = _client(tmp_path)

    response = _post(
        client,
        {"id": "event-1", "workspace_id": "workspace-a", "type": "page.content_updated", "entity": {"id": "page-1"}},
        signature="sha256=invalid",
    )

    assert response.status_code == 401
    connection = portal_connect(repository.path)
    assert connection.execute("SELECT COUNT(*) FROM notion_sync_jobs").fetchone()[0] == 0
    connection.close()


def test_unknown_or_duplicate_event_returns_accepted_without_duplicate_job(tmp_path):
    client, repository = _client(tmp_path)
    event = {"id": "event-1", "workspace_id": "workspace-a", "type": "page.properties_updated", "entity": {"id": "page-1"}}

    assert _post(client, event).status_code == 202
    assert _post(client, event).status_code == 202
    assert _post(client, {**event, "id": "event-unknown", "workspace_id": "unknown"}).status_code == 202
    connection = portal_connect(repository.path)
    assert connection.execute("SELECT COUNT(*) FROM notion_sync_jobs").fetchone()[0] == 1
    connection.close()


def test_app_registers_tenant_aware_webhook_only_when_secret_is_configured(tmp_path):
    configured = portal_app.create_app(
        settings=PortalSettings(
            database_path=str(tmp_path / "configured.sqlite3"),
            notion_webhook_secret="shhh",
        )
    )
    unconfigured = portal_app.create_app(
        settings=PortalSettings(database_path=str(tmp_path / "unconfigured.sqlite3"))
    )

    assert configured.test_client().post("/hooks/notion/events").status_code == 401
    assert unconfigured.test_client().post("/hooks/notion/events").status_code == 404
