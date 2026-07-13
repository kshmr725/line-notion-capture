from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from flask import Flask

from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.models import SourceDocument
from brain_portal.notion_webhook import create_notion_webhook_blueprint


class FakeConnector:
    def __init__(self, documents_by_id: dict[str, SourceDocument]):
        self.documents_by_id = documents_by_id
        self.retrieve_calls: list[str] = []

    def fetch_document(self, tenant_id: str, page_id: str) -> SourceDocument:
        self.retrieve_calls.append(page_id)
        return self.documents_by_id[page_id]


class FakeEmbedder:
    model_id = "fake-embedding"
    dimensions = 2

    def embed(self, text: str, task_type: str) -> list[float]:
        return [1.0, 1.0]


def doc(page_id: str = "page-1", revision: str = "new-revision") -> SourceDocument:
    return SourceDocument(
        tenant_id="tenant-notion",
        source_id=page_id,
        source_type="notion",
        canonical_ref=f"https://www.notion.so/{page_id}",
        title="Guided note",
        body="Guided body text.",
        cloud_key="ai",
        source_revision=revision,
        updated_at="2026-07-13T12:00:00+00:00",
        metadata={"summary": "Guided summary.", "concepts": ("agents",)},
    )


@pytest.fixture
def portal_repo(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    return PortalRepository(path)


@pytest.fixture
def webhook_setup(portal_repo):
    connector = FakeConnector({"page-1": doc()})
    blueprint = create_notion_webhook_blueprint(
        tenant_id="tenant-notion",
        connector=connector,
        repo=portal_repo,
        embedder=FakeEmbedder(),
        webhook_secret="shhh",
    )
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    return app.test_client(), connector, portal_repo


def _signed_post(client, secret: str, payload: dict, signature: str | None = None):
    raw = json.dumps(payload).encode("utf-8")
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/hooks/notion",
        data=raw,
        content_type="application/json",
        headers={"X-Notion-Signature": signature},
    )


def test_webhook_is_only_a_signal(webhook_setup):
    client, connector, portal_repo = webhook_setup

    response = _signed_post(
        client, "shhh", {"type": "page.content_updated", "entity": {"id": "page-1"}}
    )

    assert response.status_code == 202
    assert connector.retrieve_calls == ["page-1"]
    assert portal_repo.get_item("tenant-notion", "page-1").source_revision == "new-revision"


def test_webhook_rejects_invalid_signature(webhook_setup):
    client, connector, portal_repo = webhook_setup

    response = _signed_post(
        client,
        "shhh",
        {"type": "page.content_updated", "entity": {"id": "page-1"}},
        signature="sha256=deadbeef",
    )

    assert response.status_code == 401
    assert connector.retrieve_calls == []
    assert portal_repo.get_item("tenant-notion", "page-1") is None


def test_webhook_rejects_missing_signature(webhook_setup):
    client, connector, _ = webhook_setup

    response = client.post(
        "/hooks/notion",
        data=json.dumps({"type": "page.content_updated", "entity": {"id": "page-1"}}),
        content_type="application/json",
    )

    assert response.status_code == 401
    assert connector.retrieve_calls == []


@pytest.mark.parametrize(
    "event_type", ["page.content_updated", "page.properties_updated"]
)
def test_webhook_reindexes_on_signal_event_types(webhook_setup, event_type):
    client, connector, portal_repo = webhook_setup

    response = _signed_post(client, "shhh", {"type": event_type, "entity": {"id": "page-1"}})

    assert response.status_code == 202
    assert connector.retrieve_calls == ["page-1"]


def test_webhook_ignores_unsupported_event_types(webhook_setup):
    client, connector, portal_repo = webhook_setup

    response = _signed_post(
        client, "shhh", {"type": "database.schema_updated", "entity": {"id": "page-1"}}
    )

    assert response.status_code == 202
    assert connector.retrieve_calls == []
    assert portal_repo.get_item("tenant-notion", "page-1") is None


def test_webhook_never_trusts_a_tenant_id_in_the_body(webhook_setup):
    client, connector, portal_repo = webhook_setup

    response = _signed_post(
        client,
        "shhh",
        {
            "type": "page.content_updated",
            "entity": {"id": "page-1"},
            "tenant_id": "attacker",
        },
    )

    assert response.status_code == 202
    assert portal_repo.get_item("tenant-notion", "page-1") is not None
    assert portal_repo.get_item("attacker", "page-1") is None


def test_webhook_reindex_is_idempotent(webhook_setup):
    client, connector, portal_repo = webhook_setup

    _signed_post(client, "shhh", {"type": "page.content_updated", "entity": {"id": "page-1"}})
    _signed_post(client, "shhh", {"type": "page.content_updated", "entity": {"id": "page-1"}})

    assert connector.retrieve_calls == ["page-1", "page-1"]
    assert len(portal_repo.list_items("tenant-notion")) == 1


def test_webhook_returns_401_without_reading_payload_for_malformed_body(webhook_setup):
    client, connector, _ = webhook_setup

    response = client.post(
        "/hooks/notion",
        data=b"not-json",
        content_type="application/json",
        headers={"X-Notion-Signature": "sha256=deadbeef"},
    )

    assert response.status_code == 401
    assert connector.retrieve_calls == []
