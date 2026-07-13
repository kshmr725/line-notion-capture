from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from typing import Sequence, Union

from brain_portal.embeddings import cosine_similarity
from brain_portal.models import KnowledgeItem, SearchHit


PathLike = Union[str, os.PathLike[str]]
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


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
    tenant_key TEXT NOT NULL,
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
    tenant_key,
    chunk_text,
    content='knowledge_chunks',
    content_rowid='chunk_row_id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_insert
AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(rowid, tenant_key, chunk_text)
    VALUES (new.chunk_row_id, new.tenant_key, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_delete
AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(
        knowledge_chunks_fts, rowid, tenant_key, chunk_text
    ) VALUES ('delete', old.chunk_row_id, old.tenant_key, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_fts_update
AFTER UPDATE OF tenant_key, chunk_text ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(
        knowledge_chunks_fts, rowid, tenant_key, chunk_text
    ) VALUES ('delete', old.chunk_row_id, old.tenant_key, old.chunk_text);
    INSERT INTO knowledge_chunks_fts(rowid, tenant_key, chunk_text)
    VALUES (new.chunk_row_id, new.tenant_key, new.chunk_text);
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
        self,
        tenant_id: str,
        item: KnowledgeItem,
        chunks: Sequence[str],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if not tenant_id.strip():
            raise ValueError("trusted tenant_id is required")
        if item.tenant_id != tenant_id:
            raise ValueError("item tenant_id does not match trusted tenant_id")
        owns_connection = connection is None
        active_connection = (
            connection if connection is not None else portal_connect(self.path)
        )
        try:
            transaction = (
                active_connection
                if owns_connection
                else nullcontext(active_connection)
            )
            with transaction:
                active_connection.execute(
                    """
                    INSERT INTO tenants (tenant_id, display_name)
                    VALUES (?, ?)
                    ON CONFLICT (tenant_id) DO NOTHING
                    """,
                    (item.tenant_id, item.tenant_id),
                )
                active_connection.execute(
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
                active_connection.execute(
                    "DELETE FROM item_concepts WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                active_connection.executemany(
                    """
                    INSERT INTO item_concepts (tenant_id, source_id, concept)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (item.tenant_id, item.source_id, concept)
                        for concept in item.concepts
                    ),
                )
                active_connection.execute(
                    "DELETE FROM places WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                if item.place is not None:
                    active_connection.execute(
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
                active_connection.execute(
                    "DELETE FROM knowledge_chunks WHERE tenant_id = ? AND source_id = ?",
                    (item.tenant_id, item.source_id),
                )
                next_chunk_row_id = active_connection.execute(
                    "SELECT COALESCE(MAX(chunk_row_id), 0) + 1 FROM knowledge_chunks"
                ).fetchone()[0]
                active_connection.executemany(
                    """
                    INSERT INTO knowledge_chunks (
                        tenant_id, tenant_key, source_id, chunk_index,
                        chunk_row_id, chunk_text
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            item.tenant_id,
                            _tenant_fts_key(tenant_id),
                            item.source_id,
                            chunk_index,
                            next_chunk_row_id + chunk_index,
                            chunk_text,
                        )
                        for chunk_index, chunk_text in enumerate(chunks)
                    ),
                )
        finally:
            if owns_connection:
                active_connection.close()

    def lexical_search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        cloud_key: str | None = None,
    ) -> list[SearchHit]:
        terms = tuple(dict.fromkeys(_tokenize(query)))
        if not tenant_id.strip() or not terms or limit <= 0:
            return []
        tenant_key = _tenant_fts_key(tenant_id)
        match_query = _tenant_match_query(tenant_key, terms)
        connection = portal_connect(self.path)
        try:
            candidate_rows = connection.execute(
                """
                SELECT chunks.source_id, chunks.chunk_text
                FROM knowledge_chunks_fts AS fts
                JOIN knowledge_chunks AS chunks
                  ON chunks.chunk_row_id = fts.rowid
                 AND chunks.tenant_id = ?
                 AND chunks.tenant_key = ?
                JOIN knowledge_items AS items
                  ON items.tenant_id = chunks.tenant_id
                 AND items.source_id = chunks.source_id
                 AND items.deleted_at IS NULL
                 AND (? IS NULL OR items.cloud_key = ?)
                WHERE knowledge_chunks_fts MATCH ?
                """,
                (tenant_id, tenant_key, cloud_key, cloud_key, match_query),
            ).fetchall()
            if not candidate_rows:
                return []
            corpus_rows = connection.execute(
                """
                SELECT chunk_text
                FROM knowledge_chunks AS chunks
                JOIN knowledge_items AS items
                  ON items.tenant_id = chunks.tenant_id
                 AND items.source_id = chunks.source_id
                 AND items.deleted_at IS NULL
                 AND (? IS NULL OR items.cloud_key = ?)
                WHERE chunks.tenant_id = ? AND chunks.tenant_key = ?
                """,
                (cloud_key, cloud_key, tenant_id, tenant_key),
            ).fetchall()
            scores = _tenant_bm25_scores(terms, corpus_rows, candidate_rows)
            hits = []
            for source_id, score in sorted(
                scores.items(), key=lambda result: (-result[1], result[0])
            )[:limit]:
                row = connection.execute(
                    """
                    SELECT *
                    FROM knowledge_items
                    WHERE tenant_id = ? AND source_id = ? AND deleted_at IS NULL
                      AND (? IS NULL OR cloud_key = ?)
                    """,
                    (tenant_id, source_id, cloud_key, cloud_key),
                ).fetchone()
                if row is not None:
                    hits.append(
                        SearchHit(
                            item=self._item_from_row(connection, row),
                            score=score,
                            matched_by=("lexical",),
                        )
                    )
            return hits
        finally:
            connection.close()

    def vector_search(
        self,
        tenant_id: str,
        query_embedding: list[float],
        model_id: str,
        dimensions: int,
        limit: int = 10,
        cloud_key: str | None = None,
    ) -> list[SearchHit]:
        if (
            not tenant_id.strip()
            or not query_embedding
            or dimensions != len(query_embedding)
            or limit <= 0
        ):
            return []
        connection = portal_connect(self.path)
        try:
            rows = connection.execute(
                """
                SELECT chunks.source_id, chunks.embedding_json
                FROM knowledge_chunks AS chunks
                JOIN knowledge_items AS items
                  ON items.tenant_id = chunks.tenant_id
                 AND items.source_id = chunks.source_id
                 AND items.deleted_at IS NULL
                 AND (? IS NULL OR items.cloud_key = ?)
                WHERE chunks.tenant_id = ?
                  AND chunks.embedding_model = ?
                  AND chunks.embedding_dimensions = ?
                  AND chunks.embedding_json IS NOT NULL
                """,
                (cloud_key, cloud_key, tenant_id, model_id, dimensions),
            ).fetchall()
            scores = {}
            for row in rows:
                try:
                    raw_embedding = json.loads(row["embedding_json"])
                    if not isinstance(raw_embedding, list):
                        continue
                    embedding = [float(value) for value in raw_embedding]
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if len(embedding) != dimensions or not all(
                    math.isfinite(value) for value in embedding
                ):
                    continue
                score = cosine_similarity(query_embedding, embedding)
                scores[row["source_id"]] = max(
                    scores.get(row["source_id"], -1.0), score
                )
            hits = []
            for source_id, score in sorted(
                scores.items(), key=lambda result: (-result[1], result[0])
            )[:limit]:
                item_row = connection.execute(
                    """
                    SELECT *
                    FROM knowledge_items
                    WHERE tenant_id = ? AND source_id = ? AND deleted_at IS NULL
                      AND (? IS NULL OR cloud_key = ?)
                    """,
                    (tenant_id, source_id, cloud_key, cloud_key),
                ).fetchone()
                if item_row is not None:
                    hits.append(
                        SearchHit(
                            item=self._item_from_row(connection, item_row),
                            score=score,
                            matched_by=("semantic",),
                        )
                    )
            return hits
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


def _tenant_fts_key(tenant_id: str) -> str:
    return "tenant" + hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()


def _tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def _tenant_match_query(tenant_key: str, terms: tuple[str, ...]) -> str:
    chunk_terms = " OR ".join(f'"{term}"' for term in terms)
    return f'tenant_key:"{tenant_key}" AND chunk_text:({chunk_terms})'


def _tenant_bm25_scores(
    terms: tuple[str, ...],
    corpus_rows: Sequence[sqlite3.Row],
    candidate_rows: Sequence[sqlite3.Row],
) -> dict[str, float]:
    corpus = [_tokenize(row["chunk_text"]) for row in corpus_rows]
    document_count = len(corpus)
    average_length = (
        sum(len(tokens) for tokens in corpus) / document_count
        if document_count
        else 1.0
    )
    document_frequency = {
        term: sum(term in document for document in corpus) for term in terms
    }
    scores: dict[str, float] = {}
    for row in candidate_rows:
        document = _tokenize(row["chunk_text"])
        score = 0.0
        for term in terms:
            term_frequency = document.count(term)
            if not term_frequency:
                continue
            inverse_document_frequency = math.log(
                1.0
                + (
                    document_count - document_frequency[term] + 0.5
                )
                / (document_frequency[term] + 0.5)
            )
            denominator = term_frequency + 1.2 * (
                0.25 + 0.75 * len(document) / average_length
            )
            score += inverse_document_frequency * (
                term_frequency * 2.2 / denominator
            )
        source_id = row["source_id"]
        scores[source_id] = max(scores.get(source_id, 0.0), score)
    return scores
