import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PortalSettings:
    database_url: str = os.getenv("PORTAL_DATABASE_URL", "")
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
    notion_webhook_secret: str = os.getenv("NOTION_WEBHOOK_SECRET", "")
    notion_api_version: str = "2026-03-11"
    session_secret: str = os.getenv("PORTAL_SESSION_SECRET", "")
    session_ttl_days: int = int(os.getenv("PORTAL_SESSION_TTL_DAYS", "14"))
    magic_link_ttl_minutes: int = int(os.getenv("PORTAL_MAGIC_LINK_TTL_MINUTES", "15"))
    dev_auth: bool = os.getenv("PORTAL_DEV_AUTH", "false").strip().lower() == "true"
    smtp_host: str = os.getenv("PORTAL_SMTP_HOST", "")
    smtp_port: int = int(os.getenv("PORTAL_SMTP_PORT", "587"))
    smtp_username: str = os.getenv("PORTAL_SMTP_USERNAME", "")
    smtp_password: str = os.getenv("PORTAL_SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("PORTAL_SMTP_FROM_EMAIL", "")
    smtp_use_tls: bool = os.getenv("PORTAL_SMTP_USE_TLS", "true").strip().lower() == "true"
    smtp_timeout_seconds: float = float(os.getenv("PORTAL_SMTP_TIMEOUT_SECONDS", "20"))
    notion_oauth_client_id: str = os.getenv("NOTION_OAUTH_CLIENT_ID", "")
    notion_oauth_client_secret: str = os.getenv("NOTION_OAUTH_CLIENT_SECRET", "")
    notion_oauth_redirect_url: str = os.getenv("NOTION_OAUTH_REDIRECT_URL", "")
    oauth_state_ttl_minutes: int = int(os.getenv("PORTAL_OAUTH_STATE_TTL_MINUTES", "10"))
    token_encryption_key: str = os.getenv("PORTAL_TOKEN_ENCRYPTION_KEY", "")
    processor_token: str = os.getenv("PORTAL_PROCESSOR_TOKEN", "")
    queue_max_attempts: int = int(os.getenv("PORTAL_QUEUE_MAX_ATTEMPTS", "5"))
    queue_lease_seconds: int = int(os.getenv("PORTAL_QUEUE_LEASE_SECONDS", "300"))

    @property
    def database_target(self) -> str:
        return self.database_url.strip() or self.database_path
