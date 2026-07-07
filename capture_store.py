from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import settings


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_key TEXT NOT NULL UNIQUE,
    source_user TEXT NOT NULL,
    source_type TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    notion_url TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_captures_status ON captures(status);
CREATE INDEX IF NOT EXISTS idx_captures_created_at ON captures(created_at);
"""


@dataclass
class CaptureRecord:
    id: int
    message_key: str
    source_user: str
    source_type: str
    raw_input: str
    status: str
    title: str
    category: str
    provider: str
    notion_url: str
    error: str
    duplicate_count: int
    created_at: str
    updated_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> Path:
    return Path(settings.database_path).expanduser()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(DB_SCHEMA)


def _row_to_record(row: sqlite3.Row) -> CaptureRecord:
    return CaptureRecord(
        id=int(row["id"]),
        message_key=row["message_key"],
        source_user=row["source_user"],
        source_type=row["source_type"],
        raw_input=row["raw_input"],
        status=row["status"],
        title=row["title"],
        category=row["category"],
        provider=row["provider"],
        notion_url=row["notion_url"],
        error=row["error"],
        duplicate_count=int(row["duplicate_count"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def record_inbound(
    *,
    message_key: str,
    source_user: str,
    source_type: str,
    raw_input: str,
    payload: dict[str, Any],
) -> tuple[CaptureRecord, bool]:
    init_db()
    now = utc_now()
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO captures (
                    message_key, source_user, source_type, raw_input, status,
                    payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'received', ?, ?, ?)
                """,
                (message_key, source_user, source_type, raw_input, payload_json, now, now),
            )
            created = True
        except sqlite3.IntegrityError:
            conn.execute(
                """
                UPDATE captures
                SET duplicate_count = duplicate_count + 1, updated_at = ?
                WHERE message_key = ?
                """,
                (now, message_key),
            )
            created = False
        row = conn.execute("SELECT * FROM captures WHERE message_key = ?", (message_key,)).fetchone()
    return _row_to_record(row), created


def mark_processing(message_key: str) -> None:
    _mark(message_key, status="processing", error="")


def mark_completed(
    *,
    message_key: str,
    title: str,
    category: str,
    provider: str,
    notion_url: str,
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            UPDATE captures
            SET status = 'completed', title = ?, category = ?, provider = ?,
                notion_url = ?, error = '', updated_at = ?
            WHERE message_key = ?
            """,
            (title, category, provider, notion_url, now, message_key),
        )


def mark_failed(message_key: str, error: str) -> None:
    _mark(message_key, status="failed", error=error[:1000])


def _mark(message_key: str, *, status: str, error: str) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "UPDATE captures SET status = ?, error = ?, updated_at = ? WHERE message_key = ?",
            (status, error, now, message_key),
        )


def get_capture(message_key: str) -> CaptureRecord | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM captures WHERE message_key = ?", (message_key,)).fetchone()
    return _row_to_record(row) if row else None


def list_recent(limit: int = 25) -> list[CaptureRecord]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM captures ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def stats() -> dict[str, int]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM captures GROUP BY status").fetchall()
    data = {"received": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in rows:
        data[row["status"]] = int(row["count"])
    data["total"] = sum(data.values())
    return data
