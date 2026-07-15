from __future__ import annotations

import threading
import time

from flask import Flask

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
    repository = portal.extensions["portal_repository"]
    sync_state = {"status": "pending", "last_attempt": 0.0}
    sync_lock = threading.Lock()
    portal.extensions["shared_portal_sync"] = sync_state

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
