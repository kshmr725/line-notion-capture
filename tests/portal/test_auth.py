from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from brain_portal.auth import (
    NullMailTransport,
    create_auth_blueprint,
    create_authenticated_tenant_resolver,
    resolve_principal,
)
from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.search import SearchResults
from brain_portal.web import PortalDependencies, create_portal_blueprint


class FrozenClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    return PortalRepository(path)


@pytest.fixture
def settings():
    return PortalSettings(
        session_secret="test-secret",
        session_ttl_days=14,
        magic_link_ttl_minutes=15,
        dev_auth=True,
    )


@pytest.fixture
def clock():
    return FrozenClock(datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def transport():
    return NullMailTransport()


@pytest.fixture
def auth_app(settings, repository, clock, transport):
    app = Flask(__name__)
    app.register_blueprint(
        create_auth_blueprint(settings, repository, now=clock, mail_transport=transport)
    )
    app.register_blueprint(
        create_portal_blueprint(
            PortalDependencies(
                repository=repository,
                tenant_resolver=create_authenticated_tenant_resolver(
                    settings, repository, clock
                ),
                search_service=lambda tenant_id, query, cloud_key: SearchResults(()),
                answer_service=lambda query, hits: None,
            )
        )
    )
    app.config.update(TESTING=True)
    return app


def _invite(repository, email: str) -> None:
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "INSERT INTO beta_invites (email) VALUES (?)", (email.lower(),)
        )
    connection.close()


def _request_magic_link(client, email: str):
    return client.post("/login/request", data={"email": email})


def test_login_page_renders_for_anonymous_user(auth_app):
    response = auth_app.test_client().get("/login")
    assert response.status_code == 200
    assert "登入" in response.get_data(as_text=True)


def test_login_request_for_uninvited_email_creates_no_token_and_sends_nothing(
    auth_app, repository, transport
):
    client = auth_app.test_client()

    response = _request_magic_link(client, "stranger@example.com")

    assert response.status_code == 200
    assert transport.sent == []
    connection = portal_connect(repository.path)
    count = connection.execute("SELECT COUNT(*) FROM magic_link_tokens").fetchone()[0]
    connection.close()
    assert count == 0


def test_login_request_for_invited_email_sends_a_hashed_one_time_token(
    auth_app, repository, transport
):
    _invite(repository, "friend@example.com")
    client = auth_app.test_client()

    response = _request_magic_link(client, "Friend@Example.com")

    assert response.status_code == 200
    assert len(transport.sent) == 1
    sent_email, verify_url = transport.sent[0]
    assert sent_email == "friend@example.com"
    assert "/auth/verify?token=" in verify_url
    token = verify_url.split("token=", 1)[1]
    connection = portal_connect(repository.path)
    row = connection.execute("SELECT token_hash FROM magic_link_tokens").fetchone()
    connection.close()
    assert row is not None
    assert row["token_hash"] != token


def test_magic_link_verify_creates_a_session_and_is_single_use(
    auth_app, repository, transport
):
    _invite(repository, "friend@example.com")
    client = auth_app.test_client()
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]

    first = client.get(f"/auth/verify?token={token}", follow_redirects=False)
    assert first.status_code in (302, 303)
    assert "brain_cloud_session" in first.headers.get("Set-Cookie", "")

    connection = portal_connect(repository.path)
    used_at = connection.execute(
        "SELECT used_at FROM magic_link_tokens"
    ).fetchone()["used_at"]
    connection.close()
    assert used_at is not None

    second = client.get(f"/auth/verify?token={token}")
    assert second.status_code == 400


def test_magic_link_verify_rejects_an_expired_token(
    auth_app, repository, transport, clock
):
    _invite(repository, "friend@example.com")
    client = auth_app.test_client()
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]

    clock.advance(minutes=16)

    response = client.get(f"/auth/verify?token={token}")
    assert response.status_code == 400


def test_magic_link_verify_rejects_an_unknown_token(auth_app):
    response = auth_app.test_client().get("/auth/verify?token=not-a-real-token")
    assert response.status_code == 400


def test_resolve_principal_returns_none_without_a_session_cookie(settings, repository):
    app = Flask(__name__)

    @app.get("/whoami")
    def whoami():
        principal = resolve_principal(settings, repository)
        return {"email": principal.email if principal else None}

    response = app.test_client().get("/whoami")
    assert response.get_json() == {"email": None}


def test_resolve_principal_rejects_a_tampered_cookie(auth_app, settings, repository):
    app = auth_app

    @app.get("/whoami")
    def whoami():
        principal = resolve_principal(settings, repository)
        return {"email": principal.email if principal else None}

    client = app.test_client()
    client.set_cookie("brain_cloud_session", "not-a-valid-signed-cookie")

    response = client.get("/whoami")
    assert response.get_json() == {"email": None}


def test_session_expires_after_the_configured_ttl(
    settings, repository, transport, clock
):
    app = Flask(__name__)
    app.register_blueprint(
        create_auth_blueprint(settings, repository, now=clock, mail_transport=transport)
    )
    app.register_blueprint(
        create_portal_blueprint(
            PortalDependencies(
                repository=repository,
                tenant_resolver=create_authenticated_tenant_resolver(
                    settings, repository, clock
                ),
                search_service=lambda tenant_id, query, cloud_key: SearchResults(()),
                answer_service=lambda query, hits: None,
            )
        )
    )
    app.config.update(TESTING=True)

    @app.get("/whoami")
    def whoami():
        principal = resolve_principal(settings, repository, clock)
        return {"email": principal.email if principal else None}

    client = app.test_client()
    _invite(repository, "friend@example.com")
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    assert client.get("/whoami").get_json() == {"email": "friend@example.com"}

    clock.advance(days=settings.session_ttl_days + 1)

    assert client.get("/whoami").get_json() == {"email": None}


def test_logout_revokes_the_session(auth_app, repository, transport):
    client = auth_app.test_client()
    _invite(repository, "friend@example.com")
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    assert client.get("/onboarding").status_code == 200

    client.post("/logout")

    response = client.get("/onboarding", follow_redirects=False)
    assert response.status_code in (302, 303)


def test_onboarding_redirects_anonymous_user_to_login(auth_app):
    response = auth_app.test_client().get("/onboarding", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/login")


def test_onboarding_shows_needs_source_state_for_a_newly_verified_user(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _invite(repository, "friend@example.com")
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    response = client.get("/onboarding")

    assert response.status_code == 200
    assert "準備中" in response.get_data(as_text=True)


def test_resolve_authenticated_tenant_returns_none_before_onboarding_completes(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _invite(repository, "friend@example.com")
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    response = client.get("/")

    assert response.status_code == 401


def test_resolve_authenticated_tenant_returns_the_tenant_once_ready(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _invite(repository, "friend@example.com")
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")

    connection = portal_connect(repository.path)
    with connection:
        tenant_id = connection.execute(
            "SELECT tenant_id FROM tenant_memberships"
        ).fetchone()["tenant_id"]
        connection.execute(
            "UPDATE tenants SET onboarding_status = 'ready' WHERE tenant_id = ?",
            (tenant_id,),
        )
    connection.close()

    response = client.get("/")

    assert response.status_code == 200


def test_two_invited_users_never_share_a_tenant(auth_app, repository, transport):
    client = auth_app.test_client()
    _invite(repository, "a@example.com")
    _invite(repository, "b@example.com")

    _request_magic_link(client, "a@example.com")
    _, verify_url_a = transport.sent[0]
    client.get(f"/auth/verify?token={verify_url_a.split('token=', 1)[1]}")

    _request_magic_link(client, "b@example.com")
    _, verify_url_b = transport.sent[1]
    client.get(f"/auth/verify?token={verify_url_b.split('token=', 1)[1]}")

    connection = portal_connect(repository.path)
    tenant_ids = {
        row["tenant_id"]
        for row in connection.execute("SELECT tenant_id FROM tenant_memberships")
    }
    connection.close()
    assert len(tenant_ids) == 2
