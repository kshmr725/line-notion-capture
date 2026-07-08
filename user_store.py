from __future__ import annotations

from dataclasses import dataclass

from capture_store import connect, utc_now
from format_templates import normalize_template_key


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    line_user_id TEXT PRIMARY KEY,
    default_template TEXT NOT NULL DEFAULT 'auto',
    custom_template TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class UserPreference:
    line_user_id: str
    default_template: str
    custom_template: str
    created_at: str
    updated_at: str


def init_db() -> None:
    with connect() as conn:
        conn.executescript(DB_SCHEMA)


def get_or_create(line_user_id: str) -> UserPreference:
    init_db()
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_preferences (
                line_user_id, default_template, custom_template, created_at, updated_at
            )
            VALUES (?, 'auto', '', ?, ?)
            """,
            (line_user_id, now, now),
        )
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE line_user_id = ?",
            (line_user_id,),
        ).fetchone()
    return UserPreference(
        line_user_id=row["line_user_id"],
        default_template=row["default_template"],
        custom_template=row["custom_template"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def set_template(line_user_id: str, template_key: str, custom_template: str = "") -> UserPreference:
    normalized = normalize_template_key(template_key)
    if not normalized:
        raise ValueError("unknown template")
    get_or_create(line_user_id)
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            UPDATE user_preferences
            SET default_template = ?, custom_template = ?, updated_at = ?
            WHERE line_user_id = ?
            """,
            (normalized, custom_template.strip()[:1200] if normalized == "custom" else "", now, line_user_id),
        )
    return get_or_create(line_user_id)
