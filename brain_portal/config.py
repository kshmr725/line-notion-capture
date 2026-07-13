import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PortalSettings:
    database_path: str = os.getenv(
        "PORTAL_DATABASE_PATH", "data/brain-portal.sqlite3"
    )
    tenant_id: str = os.getenv("PORTAL_TENANT_ID", "")
    tenant_name: str = os.getenv("PORTAL_TENANT_NAME", "Kevin's Brain")
    obsidian_root: str = os.getenv("PORTAL_OBSIDIAN_ROOT", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_api_version: str = "2026-03-11"
