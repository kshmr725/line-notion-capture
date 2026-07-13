from __future__ import annotations

import pytest
from flask import Flask

from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.indexer import normalize_document
from brain_portal.models import SourceDocument, TenantContext
from brain_portal.search import SearchResults
from brain_portal.web import PortalDependencies, create_portal_blueprint
from scripts import verify_brain_portal


def _seed_item(
    repo: PortalRepository,
    tenant_id: str,
    source_id: str,
    title: str,
    body: str,
    *,
    source_type: str = "obsidian",
    canonical_ref: str | None = None,
) -> None:
    doc = SourceDocument(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type=source_type,
        canonical_ref=canonical_ref or f"obsidian://{source_id}",
        title=title,
        body=body,
        cloud_key="ai",
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
        metadata={},
    )
    item = normalize_document(doc)
    repo.upsert_item(tenant_id, item, chunks=[f"{title} {body}"])


@pytest.fixture
def shared_repo(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    _seed_item(repo, "tenant-a", "a-note", "Shared workflow A", "A secret detail")
    _seed_item(repo, "tenant-b", "b-note", "Shared workflow B", "B secret detail")
    return repo


@pytest.fixture
def portal_factory(shared_repo):
    def factory(tenant_id: str):
        def resolve_tenant() -> TenantContext:
            return TenantContext(tenant_id, tenant_id)

        def search(tid: str, query: str, cloud_key: str | None):
            hits = shared_repo.lexical_search(tid, query, cloud_key=cloud_key)
            return SearchResults(tuple(hits), degraded=True)

        dependencies = PortalDependencies(
            repository=shared_repo,
            tenant_resolver=resolve_tenant,
            search_service=search,
            answer_service=lambda query, hits: None,
        )
        app = Flask(__name__)
        app.config.update(
            PORTAL_TENANT_ID=tenant_id, PORTAL_TENANT_NAME=tenant_id, TESTING=True
        )
        app.register_blueprint(create_portal_blueprint(dependencies))
        return app.test_client()

    return factory


def test_same_query_never_crosses_tenants(portal_factory):
    tenant_a = portal_factory("tenant-a")
    tenant_b = portal_factory("tenant-b")

    assert "B secret" not in tenant_a.get("/search?q=shared").get_data(as_text=True)
    assert "A secret" not in tenant_b.get("/search?q=shared").get_data(as_text=True)


def test_item_route_never_serves_another_tenants_item(portal_factory):
    tenant_a = portal_factory("tenant-a")

    response = tenant_a.get("/item/b-note")

    assert response.status_code == 404


def test_home_recent_notes_never_cross_tenants(portal_factory):
    tenant_a = portal_factory("tenant-a")
    tenant_b = portal_factory("tenant-b")

    assert "B secret" not in tenant_a.get("/").get_data(as_text=True)
    assert "A secret" not in tenant_b.get("/").get_data(as_text=True)


def test_verify_script_reports_no_leaks_for_a_healthy_tenant(shared_repo):
    report = verify_brain_portal.verify("tenant-a", str(shared_repo.path))

    assert report["valid"] is True
    assert report["tenant_leaks"] == []
    assert report["missing_canonical_refs"] == []
    assert report["unsafe_canonical_refs"] == []
    assert report["uncited_cached_answers"] == 0


def test_verify_script_flags_missing_canonical_ref(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    _seed_item(repo, "kevin", "note-1", "Note", "Body", canonical_ref=" ")

    report = verify_brain_portal.verify("kevin", str(path))

    assert report["valid"] is False
    assert "note-1" in report["missing_canonical_refs"]


@pytest.mark.parametrize(
    ("source_type", "canonical_ref"),
    [
        ("notion", "https://evil-notion.so.attacker.example/page"),
        ("notion", "http://notion.so/page"),
        ("notion", "javascript:alert(1)"),
        ("obsidian", "https://not-obsidian-scheme/note"),
    ],
)
def test_verify_script_flags_untrusted_canonical_refs(tmp_path, source_type, canonical_ref):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    _seed_item(
        repo,
        "kevin",
        "note-1",
        "Note",
        "Body",
        source_type=source_type,
        canonical_ref=canonical_ref,
    )

    report = verify_brain_portal.verify("kevin", str(path))

    assert report["valid"] is False
    assert "note-1" in report["unsafe_canonical_refs"]


def test_verify_script_never_returns_another_tenants_data(shared_repo):
    report = verify_brain_portal.verify("tenant-a", str(shared_repo.path))

    assert report["item_count"] == 1
