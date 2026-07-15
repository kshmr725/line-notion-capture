from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from brain_portal.auth import (
    NullMailTransport,
    _consume_magic_link_token,
    begin_notion_oauth,
    complete_notion_oauth,
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
        # Auth/onboarding tests must never inherit a developer's ambient AI
        # keys and make a live embedding request during indexing.
        gemini_api_key="",
        deepseek_api_key="",
        notion_oauth_client_id="client-id",
        notion_oauth_client_secret="client-secret",
        notion_oauth_redirect_url="https://portal.example.com/oauth/notion/callback",
        oauth_state_ttl_minutes=10,
        token_encryption_key="test-token-encryption-key",
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


def _create_user(repository, user_id: str, email: str) -> None:
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "INSERT INTO users (user_id, email) VALUES (?, ?)", (user_id, email)
        )
    connection.close()


def _sign_in(client, repository, transport, email: str) -> str:
    """Invites, signs in `email`, and returns its user_id."""
    _invite(repository, email)
    _request_magic_link(client, email)
    _, verify_url = transport.sent[-1]
    token = verify_url.split("token=", 1)[1]
    client.get(f"/auth/verify?token={token}")
    connection = portal_connect(repository.path)
    user_id = connection.execute(
        "SELECT user_id FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()["user_id"]
    connection.close()
    return user_id


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


def test_concurrent_verification_of_the_same_token_creates_only_one_session(
    settings, repository, transport, clock
):
    _invite(repository, "friend@example.com")
    app = Flask(__name__)
    app.register_blueprint(
        create_auth_blueprint(settings, repository, now=clock, mail_transport=transport)
    )
    app.config.update(TESTING=True)
    client = app.test_client()
    _request_magic_link(client, "friend@example.com")
    _, verify_url = transport.sent[0]
    token = verify_url.split("token=", 1)[1]

    results: list[str | None] = []
    barrier = threading.Barrier(2)

    def race() -> None:
        barrier.wait()
        results.append(_consume_magic_link_token(settings, repository, token, clock))

    threads = [threading.Thread(target=race) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = [session_id for session_id in results if session_id is not None]
    assert len(successes) == 1
    connection = portal_connect(repository.path)
    session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    connection.close()
    assert session_count == 1


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


def _fake_token_response(**overrides):
    payload = {
        "access_token": "secret-notion-access-token",
        "workspace_id": "workspace-1",
        "workspace_name": "Kevin's Workspace",
        "bot_id": "bot-1",
    }
    payload.update(overrides)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    return FakeResponse()


def test_begin_notion_oauth_creates_a_state_bound_authorization_url(
    settings, repository, clock
):
    _create_user(repository, "user-1", "user-1@example.com")
    url = begin_notion_oauth(settings, repository, "user-1", clock)

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.hostname == "api.notion.com"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://portal.example.com/oauth/notion/callback"]
    state = params["state"][0]

    connection = portal_connect(repository.path)
    row = connection.execute(
        "SELECT user_id, provider, used_at FROM oauth_states WHERE state = ?", (state,)
    ).fetchone()
    connection.close()
    assert row["user_id"] == "user-1"
    assert row["provider"] == "notion"
    assert row["used_at"] is None


def test_begin_notion_oauth_requires_configuration(repository, clock):
    unconfigured = PortalSettings(session_secret="test-secret")

    with pytest.raises(RuntimeError):
        begin_notion_oauth(unconfigured, repository, "user-1", clock)


def test_complete_notion_oauth_rejects_an_unknown_state(settings, repository, clock):
    result = complete_notion_oauth(
        settings, repository, "user-1", "not-a-real-state", "code", clock
    )
    assert result is None


def test_complete_notion_oauth_rejects_a_state_bound_to_a_different_user(
    settings, repository, clock
):
    _create_user(repository, "user-1", "user-1@example.com")
    url = begin_notion_oauth(settings, repository, "user-1", clock)
    state = parse_qs(urlparse(url).query)["state"][0]

    result = complete_notion_oauth(settings, repository, "attacker", state, "code", clock)

    assert result is None
    connection = portal_connect(repository.path)
    used_at = connection.execute(
        "SELECT used_at FROM oauth_states WHERE state = ?", (state,)
    ).fetchone()["used_at"]
    connection.close()
    assert used_at is None


def test_complete_notion_oauth_rejects_an_expired_state(settings, repository, clock):
    _create_user(repository, "user-1", "user-1@example.com")
    url = begin_notion_oauth(settings, repository, "user-1", clock)
    state = parse_qs(urlparse(url).query)["state"][0]
    clock.advance(minutes=settings.oauth_state_ttl_minutes + 1)

    result = complete_notion_oauth(settings, repository, "user-1", state, "code", clock)

    assert result is None


def test_complete_notion_oauth_rejects_a_reused_state(settings, repository, clock, monkeypatch):
    monkeypatch.setattr(
        "brain_portal.auth.requests.post", lambda *a, **k: _fake_token_response()
    )
    _create_user(repository, "user-1", "user-1@example.com")
    url = begin_notion_oauth(settings, repository, "user-1", clock)
    state = parse_qs(urlparse(url).query)["state"][0]

    first = complete_notion_oauth(settings, repository, "user-1", state, "code", clock)
    second = complete_notion_oauth(settings, repository, "user-1", state, "code", clock)

    assert first is not None
    assert second is None


def test_complete_notion_oauth_exchanges_code_and_stores_an_encrypted_connection(
    settings, repository, clock, monkeypatch
):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _fake_token_response()

    monkeypatch.setattr("brain_portal.auth.requests.post", fake_post)
    _create_user(repository, "user-1", "user-1@example.com")
    oauth_url = begin_notion_oauth(settings, repository, "user-1", clock)
    state = parse_qs(urlparse(oauth_url).query)["state"][0]

    tenant = complete_notion_oauth(
        settings, repository, "user-1", state, "auth-code", clock
    )

    assert tenant is not None
    assert tenant.tenant_id == "user-1"
    assert captured["url"] == "https://api.notion.com/v1/oauth/token"
    assert captured["kwargs"]["auth"] == ("client-id", "client-secret")
    assert captured["kwargs"]["json"]["code"] == "auth-code"

    connection = portal_connect(repository.path)
    row = connection.execute(
        """
        SELECT config_json FROM source_connections
        WHERE tenant_id = ? AND source_type = 'notion'
        """,
        ("user-1",),
    ).fetchone()
    connection.close()
    config = json.loads(row["config_json"])
    assert config["workspace_name"] == "Kevin's Workspace"
    assert "token_ciphertext" in config
    assert "token_nonce" in config
    assert config["token_key_version"] == 1


def test_complete_notion_oauth_never_stores_the_raw_access_token(
    settings, repository, clock, monkeypatch
):
    monkeypatch.setattr(
        "brain_portal.auth.requests.post", lambda *a, **k: _fake_token_response()
    )
    _create_user(repository, "user-1", "user-1@example.com")
    url = begin_notion_oauth(settings, repository, "user-1", clock)
    state = parse_qs(urlparse(url).query)["state"][0]

    complete_notion_oauth(settings, repository, "user-1", state, "auth-code", clock)

    connection = portal_connect(repository.path)
    row = connection.execute(
        "SELECT config_json FROM source_connections WHERE tenant_id = ?", ("user-1",)
    ).fetchone()
    connection.close()
    assert "secret-notion-access-token" not in row["config_json"]


def test_oauth_start_route_redirects_anonymous_user_to_login(auth_app):
    response = auth_app.test_client().get(
        "/oauth/notion/start", follow_redirects=False
    )
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["Location"]


def test_oauth_start_route_redirects_to_notion_when_authenticated(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _sign_in(client, repository, transport, "friend@example.com")

    response = client.get("/oauth/notion/start", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["Location"].startswith(
        "https://api.notion.com/v1/oauth/authorize"
    )


def test_oauth_callback_route_redirects_to_onboarding_on_missing_code(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _sign_in(client, repository, transport, "friend@example.com")

    response = client.get("/oauth/notion/callback?error=access_denied", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding?oauth_error=1")


def test_oauth_callback_route_completes_the_flow(
    auth_app, repository, transport, monkeypatch
):
    monkeypatch.setattr(
        "brain_portal.auth.requests.post", lambda *a, **k: _fake_token_response()
    )
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")

    start_response = client.get("/oauth/notion/start", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["Location"]).query)["state"][0]

    response = client.get(
        f"/oauth/notion/callback?state={state}&code=auth-code", follow_redirects=False
    )

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding")
    connection = portal_connect(repository.path)
    row = connection.execute(
        "SELECT status FROM source_connections WHERE tenant_id = ?", (user_id,)
    ).fetchone()
    connection.close()
    assert row["status"] == "active"


def _connect_notion(client, repository, transport, monkeypatch, user_id: str) -> None:
    monkeypatch.setattr(
        "brain_portal.auth.requests.post", lambda *a, **k: _fake_token_response()
    )
    start_response = client.get("/oauth/notion/start", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["Location"]).query)["state"][0]
    client.get(f"/oauth/notion/callback?state={state}&code=auth-code")


class FakeNotionResponse:
    def __init__(self, payload: dict):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def _notion_page(page_id: str, title: str, cloud: str) -> dict:
    return {
        "id": page_id,
        "url": f"https://www.notion.so/{page_id}",
        "last_edited_time": "2026-07-14T12:00:00.000Z",
        "properties": {
            "title": {"type": "title", "title": [{"plain_text": title}]},
            "Summary": {"type": "rich_text", "rich_text": [{"plain_text": "Summary"}]},
            "Cloud": {"type": "select", "select": {"name": cloud}},
            "Concepts": {"type": "multi_select", "multi_select": []},
        },
    }


def _mock_notion_workspace(monkeypatch, pages: list[dict]) -> None:
    def fake_post(url, **kwargs):
        return FakeNotionResponse({"results": pages, "has_more": False, "next_cursor": None})

    def fake_get(url, **kwargs):
        return FakeNotionResponse(
            {
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Body text."}]},
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            }
        )

    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake_post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake_get)


def test_connect_source_page_redirects_anonymous_user_to_login(auth_app):
    response = auth_app.test_client().get(
        "/onboarding/connect-source", follow_redirects=False
    )
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["Location"]


def test_connect_source_page_redirects_to_onboarding_without_a_notion_connection(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _sign_in(client, repository, transport, "friend@example.com")

    response = client.get("/onboarding/connect-source", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding")


def test_connect_source_submit_rejects_a_blank_database_id(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)

    response = client.post(
        "/onboarding/connect-source", data={"database_id": ""}, follow_redirects=False
    )

    assert response.status_code in (302, 303)
    assert "connect-source" in response.headers["Location"]


def test_connect_source_submit_builds_a_proposal_and_advances_onboarding(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(
        monkeypatch,
        [
            _notion_page("page-1", "Restaking Thesis", "Web3 Research"),
            _notion_page("page-2", "Untagged Note", "Not A Real Cloud"),
        ],
    )

    response = client.post(
        "/onboarding/connect-source", data={"database_id": "db-1"}, follow_redirects=False
    )

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding")
    connection = portal_connect(repository.path)
    status = connection.execute(
        "SELECT onboarding_status FROM tenants WHERE tenant_id = ?", (user_id,)
    ).fetchone()["onboarding_status"]
    proposal_count = connection.execute(
        "SELECT COUNT(*) FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()[0]
    connection.close()
    assert status == "proposed"
    assert proposal_count == 1

    onboarding_html = client.get("/onboarding").get_data(as_text=True)
    assert "Restaking Thesis" in onboarding_html
    assert "Untagged Note" in onboarding_html
    assert "確認你的分類" in onboarding_html
    assert "正在建立你的 Brain Cloud" not in onboarding_html


def test_confirm_onboarding_indexes_the_proposed_items(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(
        monkeypatch, [_notion_page("page-1", "Restaking Thesis", "Web3 Research")]
    )
    client.post("/onboarding/connect-source", data={"database_id": "db-1"})
    connection = portal_connect(repository.path)
    proposal_id = connection.execute(
        "SELECT proposal_id FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()["proposal_id"]
    connection.close()

    response = client.post(
        "/onboarding/confirm",
        data={"proposal_id": proposal_id},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    from brain_portal.db import PortalRepository

    items = PortalRepository(repository.path).list_items(user_id)
    assert len(items) == 1
    assert items[0].title == "Restaking Thesis"
    connection = portal_connect(repository.path)
    status = connection.execute(
        "SELECT onboarding_status FROM tenants WHERE tenant_id = ?", (user_id,)
    ).fetchone()["onboarding_status"]
    connection.close()
    assert status == "ready"


def test_confirm_onboarding_applies_only_the_current_proposals_source_edits(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(
        monkeypatch,
        [
            _notion_page("page-1", "Restaking Thesis", "Web3 Research"),
            _notion_page("page-2", "Quiet Noodle Shop", "Food and Places"),
        ],
    )
    client.post("/onboarding/connect-source", data={"database_id": "db-1"})
    connection = portal_connect(repository.path)
    proposal_id = connection.execute(
        "SELECT proposal_id FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()["proposal_id"]
    connection.close()

    response = client.post(
        "/onboarding/confirm",
        data={
            "proposal_id": proposal_id,
            "target_key:page-1": "research",
            "label:page-1": "研究資料",
            "exclude:page-2": "1",
            "target_key:foreign-page": "food",
            "label:foreign-page": "Do not trust this",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    items = {item.source_id: item for item in PortalRepository(repository.path).list_items(user_id)}
    assert items["page-1"].cloud_key == "research"
    assert "page-2" not in items


def test_confirm_onboarding_without_a_proposal_id_redirects_safely(
    auth_app, repository, transport
):
    client = auth_app.test_client()
    _sign_in(client, repository, transport, "friend@example.com")

    response = client.post("/onboarding/confirm", data={}, follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/onboarding")


def test_confirm_onboarding_does_not_wipe_existing_items_on_an_empty_refetch(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(
        monkeypatch, [_notion_page("page-1", "Restaking Thesis", "Web3 Research")]
    )
    client.post("/onboarding/connect-source", data={"database_id": "db-1"})
    connection = portal_connect(repository.path)
    proposal_id = connection.execute(
        "SELECT proposal_id FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()["proposal_id"]
    connection.close()
    client.post("/onboarding/confirm", data={"proposal_id": proposal_id})
    assert len(PortalRepository(repository.path).list_items(user_id)) == 1

    # A later confirm whose workspace fetch legitimately comes back empty
    # (pages temporarily unshared, filters, transient state) must not wipe
    # out everything that was already indexed.
    _mock_notion_workspace(monkeypatch, [])
    client.post("/onboarding/confirm", data={"proposal_id": proposal_id})

    assert len(PortalRepository(repository.path).list_items(user_id)) == 1


def test_connect_source_page_blocks_reconnect_once_onboarding_is_ready(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(monkeypatch, [_notion_page("page-1", "Note", "Web3 Research")])
    client.post("/onboarding/connect-source", data={"database_id": "db-1"})
    connection = portal_connect(repository.path)
    proposal_id = connection.execute(
        "SELECT proposal_id FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()["proposal_id"]
    connection.close()
    client.post("/onboarding/confirm", data={"proposal_id": proposal_id})

    page_response = client.get("/onboarding/connect-source", follow_redirects=False)
    submit_response = client.post(
        "/onboarding/connect-source", data={"database_id": "db-2"}, follow_redirects=False
    )

    assert page_response.status_code in (302, 303)
    assert page_response.headers["Location"].endswith("/onboarding")
    assert submit_response.status_code in (302, 303)
    assert submit_response.headers["Location"].endswith("/onboarding")
    assert len(PortalRepository(repository.path).list_items(user_id)) == 1


def test_confirm_onboarding_blocks_once_onboarding_is_already_ready(
    auth_app, repository, transport, monkeypatch
):
    client = auth_app.test_client()
    user_id = _sign_in(client, repository, transport, "friend@example.com")
    _connect_notion(client, repository, transport, monkeypatch, user_id)
    _mock_notion_workspace(monkeypatch, [_notion_page("page-1", "Note", "Web3 Research")])
    client.post("/onboarding/connect-source", data={"database_id": "db-1"})
    connection = portal_connect(repository.path)
    proposal_id = connection.execute(
        "SELECT proposal_id FROM cloud_proposals WHERE tenant_id = ?", (user_id,)
    ).fetchone()["proposal_id"]
    connection.close()
    client.post("/onboarding/confirm", data={"proposal_id": proposal_id})

    _mock_notion_workspace(monkeypatch, [])
    response = client.post(
        "/onboarding/confirm", data={"proposal_id": proposal_id}, follow_redirects=False
    )

    assert response.status_code in (302, 303)
    assert len(PortalRepository(repository.path).list_items(user_id)) == 1
