from __future__ import annotations

from pathlib import Path

import yaml

from scripts import verify_go_live


def _portal_service() -> dict:
    config = yaml.safe_load(Path("render.yaml").read_text())
    return next(
        service for service in config["services"] if service["name"] == "brain-cloud-portal"
    )


def test_render_portal_declares_every_controlled_beta_secret_without_values():
    service = _portal_service()
    env = {entry["key"]: entry for entry in service["envVars"]}

    required_secrets = {
        "PORTAL_SESSION_SECRET",
        "PORTAL_SMTP_HOST",
        "PORTAL_SMTP_USERNAME",
        "PORTAL_SMTP_PASSWORD",
        "PORTAL_SMTP_FROM_EMAIL",
        "NOTION_OAUTH_CLIENT_ID",
        "NOTION_OAUTH_CLIENT_SECRET",
        "NOTION_OAUTH_REDIRECT_URL",
        "PORTAL_TOKEN_ENCRYPTION_KEY",
    }
    assert required_secrets <= env.keys()
    assert all(env[name].get("sync") is False for name in required_secrets)
    assert env["PORTAL_DEV_AUTH"] == {"key": "PORTAL_DEV_AUTH", "value": False}
    assert "PORTAL_TENANT_ID" not in env


class FakeResponse:
    def __init__(self, status_code: int, *, location: str = ""):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}


def test_portal_go_live_check_requires_anonymous_users_to_reach_login():
    calls = []

    def get(url: str, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(302, location="https://brain.example.com/login")

    check = verify_go_live.check_portal_auth_gate(
        "https://brain.example.com", request_get=get
    )

    assert check.ok is True
    assert check.detail == "anonymous request redirected to /login"
    assert calls == [
        ("https://brain.example.com/", {"allow_redirects": False, "timeout": 20})
    ]


def test_portal_go_live_check_fails_when_content_is_public():
    check = verify_go_live.check_portal_auth_gate(
        "https://brain.example.com",
        request_get=lambda *args, **kwargs: FakeResponse(200),
    )

    assert check.ok is False
    assert "expected login redirect" in check.detail


def test_portal_environment_check_reports_names_without_secret_values():
    environment = {
        name: f"private-{index}"
        for index, name in enumerate(verify_go_live.PORTAL_REQUIRED_ENV)
    }
    environment.pop("PORTAL_SMTP_PASSWORD")

    check = verify_go_live.check_portal_environment(environment)

    assert check.ok is False
    assert "PORTAL_SMTP_PASSWORD" in check.detail
    assert "private-" not in check.detail
