from __future__ import annotations

import pytest
from flask import Flask

import portal_app
from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db, portal_connect
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


def _multi_tenant_settings(tmp_path):
    return PortalSettings(
        database_path=str(tmp_path / "portal.sqlite3"),
        tenant_id="",
        session_secret="test-secret",
        dev_auth=True,
    )


def _sign_up_and_activate(app, client, repository, email: str) -> str:
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "INSERT INTO beta_invites (email) VALUES (?)", (email.lower(),)
        )
    connection.close()

    client.post("/login/request", data={"email": email})
    transport = app.extensions["mail_transport"]
    _, verify_url = transport.sent[-1]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    connection = portal_connect(repository.path)
    with connection:
        tenant_id = connection.execute(
            """
            SELECT tenant_memberships.tenant_id AS tenant_id
            FROM tenant_memberships
            JOIN users ON users.user_id = tenant_memberships.user_id
            WHERE users.email = ?
            """,
            (email.lower(),),
        ).fetchone()["tenant_id"]
        connection.execute(
            "UPDATE tenants SET onboarding_status = 'ready' WHERE tenant_id = ?",
            (tenant_id,),
        )
    connection.close()
    return tenant_id


def test_anonymous_request_to_protected_route_redirects_to_login(tmp_path):
    init_portal_db(tmp_path / "portal.sqlite3")
    app = portal_app.create_app(settings=_multi_tenant_settings(tmp_path))
    app.config.update(TESTING=True)

    response = app.test_client().get("/", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert "/login" in response.headers["Location"]


def test_authenticated_user_without_a_ready_tenant_redirects_to_onboarding(tmp_path):
    database_path = tmp_path / "portal.sqlite3"
    init_portal_db(database_path)
    settings = _multi_tenant_settings(tmp_path)
    app = portal_app.create_app(settings=settings)
    app.config.update(TESTING=True)
    repository = PortalRepository(database_path)
    client = app.test_client()

    connection = portal_connect(database_path)
    with connection:
        connection.execute(
            "INSERT INTO beta_invites (email) VALUES ('friend@example.com')"
        )
    connection.close()
    client.post("/login/request", data={"email": "friend@example.com"})
    transport = app.extensions["mail_transport"]
    _, verify_url = transport.sent[-1]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding")


def test_two_authenticated_users_never_see_each_others_tenant_data(tmp_path):
    database_path = tmp_path / "portal.sqlite3"
    init_portal_db(database_path)
    settings = _multi_tenant_settings(tmp_path)
    app = portal_app.create_app(settings=settings)
    app.config.update(TESTING=True)
    repository = PortalRepository(database_path)

    client_a = app.test_client()
    tenant_a = _sign_up_and_activate(app, client_a, repository, "a@example.com")
    _seed_item(repository, tenant_a, "a-note", "A workflow", "A secret detail")

    client_b = app.test_client()
    tenant_b = _sign_up_and_activate(app, client_b, repository, "b@example.com")
    _seed_item(repository, tenant_b, "b-note", "B workflow", "B secret detail")

    assert tenant_a != tenant_b

    home_a = client_a.get("/").get_data(as_text=True)
    home_b = client_b.get("/").get_data(as_text=True)
    assert "B secret" not in home_a
    assert "A secret" not in home_b

    assert client_a.get("/item/b-note").status_code == 404
    assert client_b.get("/item/a-note").status_code == 404
