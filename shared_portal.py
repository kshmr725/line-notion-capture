from __future__ import annotations

import threading
import time
import hashlib
import hmac

from flask import Flask, redirect, render_template_string, request, session, url_for

from brain_portal.config import PortalSettings
from brain_portal.connectors.notion import NotionConnector
from brain_portal.db import PortalRepository
from brain_portal.indexer import run_index
from portal_app import create_app


SHARED_TENANT_ID = "shared-brain"
SYNC_INTERVAL_SECONDS = 600


def create_shared_portal(
    existing_settings,
    *,
    database_path: str = "data/shared-brain-portal.sqlite3",
    connector_factory=NotionConnector,
    access_code: str | None = None,
) -> Flask:
    portal_settings = PortalSettings(
        database_path=database_path,
        tenant_id=SHARED_TENANT_ID,
        tenant_name="Second Brain",
        gemini_api_key=existing_settings.gemini_api_key,
        deepseek_api_key=existing_settings.deepseek_api_key,
        notion_token=existing_settings.notion_token,
    )
    portal = create_app(portal_settings)
    if access_code is not None:
        portal.secret_key = hashlib.sha256(
            ("brain-cloud-session:" + access_code).encode("utf-8")
        ).hexdigest()
    repository = portal.extensions["portal_repository"]
    sync_state = {"status": "pending", "last_attempt": 0.0}
    sync_lock = threading.Lock()
    portal.extensions["shared_portal_sync"] = sync_state

    @portal.route("/access", methods=["GET", "POST"])
    def shared_access():
        if not access_code:
            return ("Second Brain 尚未開放，請設定 BRAIN_ACCESS_CODE。", 503)
        error = ""
        if request.method == "POST":
            provided = request.form.get("access_code", "")
            if hmac.compare_digest(provided, access_code):
                session["brain_access"] = True
                return redirect(url_for("portal.home"))
            error = "登入碼不正確"
        return render_template_string(
            ACCESS_TEMPLATE,
            error=error,
        )

    @portal.before_request
    def require_shared_access():
        if access_code is None or request.endpoint in {"shared_access", "portal.static"}:
            return None
        if not access_code:
            return ("Second Brain 尚未開放，請設定 BRAIN_ACCESS_CODE。", 503)
        if session.get("brain_access") is not True:
            return redirect(url_for("shared_access"))
        return None

    @portal.before_request
    def refresh_shared_notion_projection():
        if not existing_settings.notion_token or not existing_settings.notion_database_id:
            sync_state["status"] = "missing_notion"
            return ("Notion 尚未連接，請確認既有 NOTION_TOKEN 與 NOTION_DATABASE_ID。", 503)
        now = time.monotonic()
        if (
            sync_state["status"] == "ready"
            and now - sync_state["last_attempt"] < SYNC_INTERVAL_SECONDS
        ):
            return None
        if not sync_lock.acquire(blocking=False):
            return None
        try:
            sync_state["last_attempt"] = now
            connector = connector_factory(
                token=existing_settings.notion_token,
                database_id=existing_settings.notion_database_id,
                api_version="2022-06-28",
            )
            report = run_index(SHARED_TENANT_ID, connector, repository, None)
            sync_state["status"] = "ready" if report.failed == 0 else "stale"
        finally:
            sync_lock.release()
        return None

    return portal


ACCESS_TEMPLATE = """
<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>進入 Second Brain</title><style>
body{margin:0;background:#f4f0e8;color:#202124;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{min-height:100vh;display:grid;place-items:center;padding:24px}.card{width:min(420px,100%);background:#fffdf8;border:1px solid #d8d0c2;border-radius:20px;padding:32px;box-shadow:0 20px 60px rgba(40,32,20,.1)}
h1{font-size:32px;margin:0 0 10px}p{color:#6b655d;line-height:1.6}label{display:block;font-weight:700;margin:24px 0 8px}input{width:100%;box-sizing:border-box;padding:14px;border:1px solid #bdb5a8;border-radius:12px;font-size:18px}button{width:100%;margin-top:14px;padding:14px;border:0;border-radius:12px;background:#222;color:white;font-size:17px;font-weight:700}.error{color:#a13b2b}
</style></head><body><main><form class="card" method="post"><h1>Second Brain</h1><p>輸入 Beta 使用者登入碼。</p>{% if error %}<p class="error">{{ error }}</p>{% endif %}<label for="access_code">登入碼</label><input id="access_code" name="access_code" type="password" required autocomplete="current-password"><button type="submit">進入資料庫</button></form></main></body></html>
"""
