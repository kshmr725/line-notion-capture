from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from brain_portal.connectors.base import SourceConnector
from brain_portal.db import PortalRepository, portal_connect
from brain_portal.models import KnowledgeItem, SourceDocument


class EmbeddingProvider(Protocol):
    def embed(self, text: str, task_type: str) -> list[float]: ...


@dataclass(frozen=True)
class IndexReport:
    indexed: int
    unchanged: int
    deleted: int
    failed: int


def normalize_document(doc: SourceDocument) -> KnowledgeItem:
    paragraphs = [part.strip() for part in doc.body.split("\n\n") if part.strip()]
    summary = next((p for p in paragraphs if not p.startswith("#")), doc.title)[:500]
    return KnowledgeItem(
        tenant_id=doc.tenant_id,
        source_id=doc.source_id,
        source_type=doc.source_type,
        canonical_ref=doc.canonical_ref,
        title=doc.title,
        summary=summary,
        body=doc.body,
        cloud_key=doc.cloud_key,
        item_type=str(doc.metadata.get("item_type") or "research"),
        concepts=tuple(doc.metadata.get("concepts") or ()),
        place=(
            doc.metadata.get("place")
            if isinstance(doc.metadata.get("place"), dict)
            else None
        ),
        source_revision=doc.source_revision,
        updated_at=doc.updated_at,
    )


def run_index(
    tenant_id: str,
    connector: SourceConnector,
    repo: PortalRepository,
    embedder: EmbeddingProvider,
) -> IndexReport:
    if not tenant_id.strip():
        raise ValueError("trusted tenant_id is required")
    configured_source_type = str(getattr(connector, "source_type", "unknown"))
    run_id = _begin_sync(repo, tenant_id, configured_source_type)
    try:
        documents = list(connector.iter_documents(tenant_id))
    except Exception as error:
        report = IndexReport(indexed=0, unchanged=0, deleted=0, failed=1)
        _finish_sync(repo, tenant_id, run_id, "stale", report, str(error))
        return report

    source_types = {doc.source_type for doc in documents}
    source_type = configured_source_type
    if source_type == "unknown" and len(source_types) == 1:
        source_type = next(iter(source_types))
    existing = {item.source_id: item for item in repo.list_items(tenant_id)}
    indexed = 0
    unchanged = 0
    failed = 0
    seen_source_ids = {doc.source_id for doc in documents}
    for doc in documents:
        if doc.tenant_id != tenant_id:
            failed += 1
            continue
        if doc.source_id in existing and (
            existing[doc.source_id].source_revision == doc.source_revision
        ):
            unchanged += 1
            continue
        try:
            item = normalize_document(doc)
            chunks = _chunk_item(item)
            embeddings = [
                [float(value) for value in embedder.embed(chunk, "RETRIEVAL_DOCUMENT")]
                for chunk in chunks
            ]
            repo.upsert_item(tenant_id, item, chunks)
            _persist_embeddings(
                repo,
                tenant_id,
                item.source_id,
                embeddings,
                str(getattr(embedder, "model_id", type(embedder).__name__)),
            )
            indexed += 1
        except Exception:
            failed += 1

    deleted = _soft_delete_missing(
        repo, tenant_id, source_type, seen_source_ids
    )
    report = IndexReport(
        indexed=indexed,
        unchanged=unchanged,
        deleted=deleted,
        failed=failed,
    )
    _finish_sync(repo, tenant_id, run_id, "success", report)
    return report


def _chunk_item(item: KnowledgeItem, max_chars: int = 2000) -> list[str]:
    content = f"{item.title}\n\n{item.body}".strip()
    chunks = [
        content[index : index + max_chars]
        for index in range(0, len(content), max_chars)
    ]
    return chunks or [item.title]


def _begin_sync(repo: PortalRepository, tenant_id: str, source_type: str) -> str:
    run_id = uuid4().hex
    connection = portal_connect(repo.path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO tenants (tenant_id, display_name)
                VALUES (?, ?)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tenant_id, tenant_id),
            )
            connection.execute(
                """
                INSERT INTO sync_runs (
                    tenant_id, run_id, source_type, status, started_at
                ) VALUES (?, ?, ?, 'running', ?)
                """,
                (tenant_id, run_id, source_type, _now()),
            )
    finally:
        connection.close()
    return run_id


def _finish_sync(
    repo: PortalRepository,
    tenant_id: str,
    run_id: str,
    status: str,
    report: IndexReport,
    error_summary: str | None = None,
) -> None:
    connection = portal_connect(repo.path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE sync_runs
                SET status = ?, finished_at = ?, indexed_count = ?,
                    unchanged_count = ?, deleted_count = ?, failed_count = ?,
                    error_summary = ?
                WHERE tenant_id = ? AND run_id = ?
                """,
                (
                    status,
                    _now(),
                    report.indexed,
                    report.unchanged,
                    report.deleted,
                    report.failed,
                    error_summary,
                    tenant_id,
                    run_id,
                ),
            )
    finally:
        connection.close()


def _persist_embeddings(
    repo: PortalRepository,
    tenant_id: str,
    source_id: str,
    embeddings: list[list[float]],
    model_id: str,
) -> None:
    connection = portal_connect(repo.path)
    try:
        with connection:
            rows = connection.execute(
                """
                SELECT chunk_index
                FROM knowledge_chunks
                WHERE tenant_id = ? AND source_id = ?
                ORDER BY chunk_index
                """,
                (tenant_id, source_id),
            ).fetchall()
            if len(rows) != len(embeddings):
                raise RuntimeError("chunk and embedding counts differ")
            for row, embedding in zip(rows, embeddings):
                connection.execute(
                    """
                    UPDATE knowledge_chunks
                    SET embedding_json = ?, embedding_model = ?,
                        embedding_dimensions = ?
                    WHERE tenant_id = ? AND source_id = ? AND chunk_index = ?
                    """,
                    (
                        json.dumps(embedding),
                        model_id,
                        len(embedding),
                        tenant_id,
                        source_id,
                        row["chunk_index"],
                    ),
                )
    finally:
        connection.close()


def _soft_delete_missing(
    repo: PortalRepository,
    tenant_id: str,
    source_type: str,
    seen_source_ids: set[str],
) -> int:
    if source_type == "unknown":
        return 0
    parameters = [tenant_id, source_type]
    exclusion = ""
    if seen_source_ids:
        placeholders = ", ".join("?" for _ in seen_source_ids)
        exclusion = f" AND source_id NOT IN ({placeholders})"
        parameters.extend(sorted(seen_source_ids))
    connection = portal_connect(repo.path)
    try:
        with connection:
            cursor = connection.execute(
                """
                UPDATE knowledge_items
                SET deleted_at = ?
                WHERE tenant_id = ? AND source_type = ? AND deleted_at IS NULL
                """
                + exclusion,
                [_now(), *parameters],
            )
            return max(cursor.rowcount, 0)
    finally:
        connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
