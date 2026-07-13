from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Sequence, Union

from brain_portal.models import KnowledgeItem


PathLike = Union[str, os.PathLike[str]]


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS source_connections (
    tenant_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    last_synced_at TEXT,
    PRIMARY KEY (tenant_id, source_type, connection_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_items (
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    canonical_ref TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    cloud_key TEXT NOT NULL,
    item_type TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    PRIMARY KEY (tenant_id, source_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS knowledge_items_cloud_idx
    ON knowledge_items (tenant_id, cloud_key, updated_at DESC);
CREATE INDEX IF NOT EXISTS knowledge_items_revision_idx
    ON knowledge_items (tenant_id, source_type, source_revision);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_row_id INTEGER NOT NULL UNIQUE,
    chunk_text TEXT NOT NULL,
    embedding_json TEXT,
    embedding_model TEXT,
    embedding_dimensions INTEGER,
    PRIMARY KEY (tenant_id, source_id, chunk_index),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES knowledge_items (tenant_id, source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_concepts (
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    concept TEXT NOT NULL,
    PRIMARY KEY (tenant_id, source_id, concept),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES knowledge_items (tenant_id, source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS places (
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    place_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, source_id),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES knowledge_items (tenant_id, source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    indexed_count INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
    chunk_text,
    content='knowledge_chunks',
    content_rowid='chunk_row_id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_insert
AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(rowid, chunk_text)
    VALUES (new.chunk_row_id, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_delete
AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, chunk_text)
    VALUES ('delete', old.chunk_row_id, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_update
AFTER UPDATE OF chunk_text ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, chunk_text)
    VALUES ('delete', old.chunk_row_id, old.chunk_text);
    INSERT INTO knowledge_chunks_fts(rowid, chunk_text)
    VALUES (new.chunk_row_id, new.chunk_text);
END;
"""


def portal_connect(path: PathLike) -> sqlite3.Connection:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_portal_db(path: PathLike) -> None:
    connection = portal_connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


class PortalRepository:
    def __init__(self, path: PathLike):
        self.path = path

    def upsert_item(
        self, item: KnowledgeItem, chunks: Sequence[str]
    ) -> None:
        connection = portal_connect(self.path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO tenants (tenant_id, display_name)
                    VALUES (?, ?)
                    ON CONFLICT (tenant_id) DO NOTHING
                    """,
                    (item.tenant_id, item.tenant_id),
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_items (
                        tenant_id, source_id, source_type, canonical_ref, title,
                        summary, body, cloud_key, item_type, source_revision,
                        updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT (tenant_id, source_id) DO UPDATE SET
                        source_type = excluded.source_type,
                        canonical_ref = excluded.canonical_ref,
                        title = excluded.title,
                        summary = excluded.summary,
                        body = excluded.body,
                        cloud_key = excluded.cloud_key,
                        item_type = excluded.item_type,
                        source_revision = excluded.source_revision,
                        updated_at = excluded.updated_at,
                        deleted_at = NULL
                    """,
                    (
                        item.tenant_id,
                        item.source_id,
                        item.source_type,
                        item.canonical_ref,
                        item.title,
                        item.summary,
                        item.body,
                        item.cloud_key,
                        item.item_type,
                        item.source_revision,
                        item.updated_at,
                    ),
                )
                connection.execute(
                    "DELETE FROM item_concepts WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                connection.executemany(
                    """
                    INSERT INTO item_concepts (tenant_id, source_id, concept)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (item.tenant_id, item.source_id, concept)
                        for concept in item.concepts
                    ),
                )
                connection.execute(
                    "DELETE FROM places WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                if item.place is not None:
                    connection.execute(
                        """
                        INSERT INTO places (tenant_id, source_id, place_json)
                        VALUES (?, ?, ?)
                        """,
                        (
                            item.tenant_id,
                            item.source_id,
                            json.dumps(item.place, sort_keys=True),
                        ),
                    )
                connection.execute(
                    "DELETE FROM knowledge_chunks WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                next_chunk_row_id = connection.execute(
                    "SELECT COALESCE(MAX(chunk_row_id), 0) + 1 FROM knowledge_chunks"
                ).fetchone()[0]
                connection.executemany(
                    """
                    INSERT INTO knowledge_chunks (
                        tenant_id, source_id, chunk_index, chunk_row_id, chunk_text
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            item.tenant_id,
                            item.source_id,
                            chunk_index,
                            next_chunk_row_id + chunk_index,
                            chunk_text,
                        )
                        for chunk_index, chunk_text in enumerate(chunks)
                    ),
                )
        finally:
            connection.close()

    def list_items(self, tenant_id: str) -> list[KnowledgeItem]:
        connection = portal_connect(self.path)
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM knowledge_items
                WHERE tenant_id = ? AND deleted_at IS NULL
                ORDER BY updated_at DESC, source_id ASC
                """,
                (tenant_id,),
            ).fetchall()
            return [self._item_from_row(connection, row) for row in rows]
        finally:
            connection.close()

    @staticmethod
    def _item_from_row(
        connection: sqlite3.Connection, row: sqlite3.Row
    ) -> KnowledgeItem:
        concepts = connection.execute(
            """
            SELECT concept
            FROM item_concepts
            WHERE tenant_id = ? AND source_id = ?
            ORDER BY concept
            """,
            (row["tenant_id"], row["source_id"]),
        ).fetchall()
        place_row = connection.execute(
            """
            SELECT place_json
            FROM places
            WHERE tenant_id = ? AND source_id = ?
            """,
            (row["tenant_id"], row["source_id"]),
        ).fetchone()
        return KnowledgeItem(
            tenant_id=row["tenant_id"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            canonical_ref=row["canonical_ref"],
            title=row["title"],
            summary=row["summary"],
            body=row["body"],
            cloud_key=row["cloud_key"],
            item_type=row["item_type"],
            concepts=tuple(concept["concept"] for concept in concepts),
            place=json.loads(place_row["place_json"]) if place_row else None,
            source_revision=row["source_revision"],
            updated_at=row["updated_at"],
        )
