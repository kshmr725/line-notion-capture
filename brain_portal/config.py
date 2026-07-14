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
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    ai_timeout_seconds: float = float(os.getenv("PORTAL_AI_TIMEOUT_SECONDS", "20"))
    gemini_answer_model: str = os.getenv(
        "PORTAL_GEMINI_ANSWER_MODEL", "gemini-2.5-flash"
    )
    deepseek_answer_model: str = os.getenv(
        "PORTAL_DEEPSEEK_ANSWER_MODEL", "deepseek-chat"
    )
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_api_version: str = "2026-03-11"
    session_secret: str = os.getenv("PORTAL_SESSION_SECRET", "")
    session_ttl_days: int = int(os.getenv("PORTAL_SESSION_TTL_DAYS", "14"))
    magic_link_ttl_minutes: int = int(os.getenv("PORTAL_MAGIC_LINK_TTL_MINUTES", "15"))
    dev_auth: bool = os.getenv("PORTAL_DEV_AUTH", "false").strip().lower() == "true"
