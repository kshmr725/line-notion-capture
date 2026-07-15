from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


load_dotenv()


PORTAL_REQUIRED_ENV = (
    "PORTAL_DATABASE_URL",
    "PORTAL_SESSION_SECRET",
    "PORTAL_SMTP_HOST",
    "PORTAL_SMTP_USERNAME",
    "PORTAL_SMTP_PASSWORD",
    "PORTAL_SMTP_FROM_EMAIL",
    "NOTION_OAUTH_CLIENT_ID",
    "NOTION_OAUTH_CLIENT_SECRET",
    "NOTION_OAUTH_REDIRECT_URL",
    "PORTAL_TOKEN_ENCRYPTION_KEY",
    "NOTION_WEBHOOK_SECRET",
    "PORTAL_PROCESSOR_TOKEN",
)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_health(base_url: str) -> Check:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/health", timeout=20)
        response.raise_for_status()
        return Check("Render health", True, response.text[:200])
    except Exception as exc:
        return Check("Render health", False, f"{type(exc).__name__}: {exc}")


def check_line_token() -> Check:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        return Check("LINE access token", False, "missing LINE_CHANNEL_ACCESS_TOKEN")
    try:
        response = requests.get(
            "https://api.line.me/v2/bot/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        response.raise_for_status()
        return Check("LINE access token", True, response.text[:300])
    except Exception as exc:
        return Check("LINE access token", False, f"{type(exc).__name__}: {exc}")


def check_notion_database() -> Check:
    token = os.getenv("NOTION_TOKEN", "")
    database_id = os.getenv("NOTION_DATABASE_ID", "")
    if not token or not database_id:
        return Check("Notion database", False, "missing NOTION_TOKEN or NOTION_DATABASE_ID")
    try:
        response = requests.get(
            f"https://api.notion.com/v1/databases/{database_id}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"},
            timeout=20,
        )
        response.raise_for_status()
        return Check("Notion database", True, response.text[:300])
    except Exception as exc:
        return Check("Notion database", False, f"{type(exc).__name__}: {exc}")


def check_portal_environment(environment=None) -> Check:
    values = environment if environment is not None else os.environ
    missing = [name for name in PORTAL_REQUIRED_ENV if not values.get(name, "").strip()]
    if missing:
        return Check("Portal environment", False, "missing " + ", ".join(missing))
    if values.get("PORTAL_DEV_AUTH", "false").strip().lower() == "true":
        return Check("Portal environment", False, "PORTAL_DEV_AUTH must be false")
    if values.get("PORTAL_TENANT_ID", "").strip():
        return Check("Portal environment", False, "PORTAL_TENANT_ID must be empty")
    database_url = values.get("PORTAL_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        return Check(
            "Portal environment", False, "PORTAL_DATABASE_URL must use PostgreSQL"
        )
    redirect_url = values.get("NOTION_OAUTH_REDIRECT_URL", "").strip()
    if not redirect_url.startswith("https://"):
        return Check(
            "Portal environment", False, "NOTION_OAUTH_REDIRECT_URL must use HTTPS"
        )
    return Check("Portal environment", True, "required names are configured")


def check_portal_auth_gate(base_url: str, *, request_get=requests.get) -> Check:
    try:
        response = request_get(
            f"{base_url.rstrip('/')}/", allow_redirects=False, timeout=20
        )
    except Exception as exc:
        return Check("Portal auth gate", False, f"{type(exc).__name__}")
    location = response.headers.get("Location", "")
    if response.status_code in (301, 302, 303, 307, 308) and "/login" in location:
        return Check("Portal auth gate", True, "anonymous request redirected to /login")
    return Check(
        "Portal auth gate",
        False,
        f"expected login redirect, received HTTP {response.status_code}",
    )


def check_portal_login_page(base_url: str, *, request_get=requests.get) -> Check:
    try:
        response = request_get(f"{base_url.rstrip('/')}/login", timeout=20)
    except Exception as exc:
        return Check("Portal login page", False, f"{type(exc).__name__}")
    return Check(
        "Portal login page",
        response.status_code == 200,
        f"HTTP {response.status_code}",
    )


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--portal":
        checks = [
            check_portal_environment(),
            check_portal_auth_gate(sys.argv[2]),
            check_portal_login_page(sys.argv[2]),
        ]
    elif len(sys.argv) == 2:
        base_url = sys.argv[1]
        checks = [check_health(base_url), check_line_token(), check_notion_database()]
    else:
        print(
            "Usage: python scripts/verify_go_live.py [--portal] https://your-render-url"
        )
        return 2
    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        print(f"[{mark}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
