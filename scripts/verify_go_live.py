from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


load_dotenv()


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


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_go_live.py https://your-render-url")
        return 2
    base_url = sys.argv[1]
    checks = [check_health(base_url), check_line_token(), check_notion_database()]
    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        print(f"[{mark}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
