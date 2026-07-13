from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from brain_portal.connectors.base import SourceConnector
from brain_portal.db import PortalRepository, portal_connect
from brain_portal.models import KnowledgeItem, SourceDocument


class EmbeddingProvider(Protocol):
    model_id: str
    dimensions: int

    def embed(self, text: str, task_type: str) -> list[float]: ...


@dataclass(frozen=True)
class IndexReport:
    indexed: int
    unchanged: int
    deleted: int
    failed: int


def normalize_document(doc: SourceDocument) -> KnowledgeItem:
    paragraphs = [part.strip() for part in doc.body.split("\n\n") if part.strip()]
    metadata_summary = doc.metadata.get("summary")
    summary = (
        metadata_summary.strip()[:500]
        if isinstance(metadata_summary, str) and metadata_summary.strip()
        else next((p for p in paragraphs if not p.startswith("#")), doc.title)[:500]
    )
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
    model_id, dimensions = _embedding_space(embedder)
    source_type = connector.source_type.strip()
    if not source_type:
        raise ValueError("connector source_type is required")
    run_id = _begin_sync(repo, tenant_id, source_type)
    try:
        documents = list(connector.iter_documents(tenant_id))
    except Exception as error:
        report = IndexReport(indexed=0, unchanged=0, deleted=0, failed=1)
        _finish_sync(
            repo,
            tenant_id,
            run_id,
            "stale",
            report,
            _bounded_diagnostic(type(error).__name__, str(error)),
        )
        return report

    existing = {item.source_id: item for item in repo.list_items(tenant_id)}
    unchanged = 0
    failed = 0
    diagnostics = []
    prepared = []
    seen_source_ids = {doc.source_id for doc in documents}
    for doc in documents:
        if doc.tenant_id != tenant_id:
            failed += 1
            diagnostics.append(f"{doc.source_id}: tenant mismatch")
            continue
        if doc.source_type != source_type:
            failed += 1
            diagnostics.append(f"{doc.source_id}: source_type mismatch")
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
            if any(
                len(embedding) != dimensions
                or not all(math.isfinite(value) for value in embedding)
                for embedding in embeddings
            ):
                raise ValueError("embedding vector does not match provider space")
            prepared.append((item, chunks, embeddings))
        except Exception as error:
            failed += 1
            diagnostics.append(
                _bounded_diagnostic(doc.source_id, type(error).__name__)
            )

    connection = portal_connect(repo.path)
    try:
        with connection:
            for item, chunks, embeddings in prepared:
                repo.upsert_item(
                    tenant_id,
                    item,
                    chunks,
                    connection=connection,
                )
                _persist_embeddings(
                    connection,
                    tenant_id,
                    item.source_id,
                    embeddings,
                    model_id,
                )
            deleted = _soft_delete_missing(
                connection, tenant_id, source_type, seen_source_ids
            )
    except Exception as error:
        report = IndexReport(
            indexed=0,
            unchanged=unchanged,
            deleted=0,
            failed=failed + 1,
        )
        _finish_sync(
            repo,
            tenant_id,
            run_id,
            "stale",
            report,
            _bounded_diagnostic(type(error).__name__, str(error)),
        )
        return report
    finally:
        connection.close()

    report = IndexReport(
        indexed=len(prepared),
        unchanged=unchanged,
        deleted=deleted,
        failed=failed,
    )
    _finish_sync(
        repo,
        tenant_id,
        run_id,
        "success",
        report,
        _join_diagnostics(diagnostics),
    )
    return report


def index_document(
    tenant_id: str,
    doc: SourceDocument,
    repo: PortalRepository,
    embedder: EmbeddingProvider | None,
) -> IndexReport:
    if not tenant_id.strip():
        raise ValueError("trusted tenant_id is required")
    if doc.tenant_id != tenant_id:
        raise ValueError("document tenant_id does not match trusted tenant_id")
    source_type = doc.source_type.strip()
    if not source_type:
        raise ValueError("document source_type is required")

    run_id = _begin_sync(repo, tenant_id, source_type)
    existing = repo.get_item(tenant_id, doc.source_id)
    if existing is not None and existing.source_revision == doc.source_revision:
        report = IndexReport(indexed=0, unchanged=1, deleted=0, failed=0)
        _finish_sync(repo, tenant_id, run_id, "success", report)
        return report

    try:
        item = normalize_document(doc)
        chunks = _chunk_item(item)
        embeddings = None
        model_id = None
        if embedder is not None:
            model_id, dimensions = _embedding_space(embedder)
            embeddings = [
                [float(value) for value in embedder.embed(chunk, "RETRIEVAL_DOCUMENT")]
                for chunk in chunks
            ]
            if any(
                len(embedding) != dimensions
                or not all(math.isfinite(value) for value in embedding)
                for embedding in embeddings
            ):
                raise ValueError("embedding vector does not match provider space")
        connection = portal_connect(repo.path)
        try:
            with connection:
                repo.upsert_item(tenant_id, item, chunks, connection=connection)
                if embeddings is not None:
                    _persist_embeddings(
                        connection, tenant_id, item.source_id, embeddings, model_id
                    )
        finally:
            connection.close()
    except PermissionError as error:
        report = IndexReport(indexed=0, unchanged=0, deleted=0, failed=1)
        _finish_sync(
            repo,
            tenant_id,
            run_id,
            "permission_required",
            report,
            _bounded_diagnostic(type(error).__name__, str(error)),
        )
        return report
    except Exception as error:
        report = IndexReport(indexed=0, unchanged=0, deleted=0, failed=1)
        _finish_sync(
            repo,
            tenant_id,
            run_id,
            "stale",
            report,
            _bounded_diagnostic(type(error).__name__, str(error)),
        )
        return report

    report = IndexReport(indexed=1, unchanged=0, deleted=0, failed=0)
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
    connection: sqlite3.Connection,
    tenant_id: str,
    source_id: str,
    embeddings: list[list[float]],
    model_id: str,
) -> None:
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


def _soft_delete_missing(
    connection: sqlite3.Connection,
    tenant_id: str,
    source_type: str,
    seen_source_ids: set[str],
) -> int:
    parameters = [tenant_id, source_type]
    exclusion = ""
    if seen_source_ids:
        placeholders = ", ".join("?" for _ in seen_source_ids)
        exclusion = f" AND source_id NOT IN ({placeholders})"
        parameters.extend(sorted(seen_source_ids))
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


def _join_diagnostics(diagnostics: list[str]) -> str | None:
    return "; ".join(diagnostics)[:500] or None


def _bounded_diagnostic(label: str, detail: str) -> str:
    return f"{label}: {detail}"[:500]


def _embedding_space(embedder: EmbeddingProvider) -> tuple[str, int]:
    model_id = embedder.model_id.strip()
    dimensions = embedder.dimensions
    if not model_id or not isinstance(dimensions, int) or dimensions <= 0:
        raise ValueError("embedding provider model_id and dimensions are required")
    return model_id, dimensions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
