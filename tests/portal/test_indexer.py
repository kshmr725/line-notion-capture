import json
from dataclasses import replace

import pytest

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.connectors.base import SourceConnector
from brain_portal.indexer import IndexReport, normalize_document, run_index
from brain_portal.models import SourceDocument


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, text: str, task_type: str) -> list[float]:
        self.calls.append((text, task_type))
        return [float(len(text)), 1.0]


class FakeConnector:
    source_type = "obsidian"

    def __init__(self, documents):
        self.documents = documents

    def iter_documents(self, tenant_id: str):
        yield from self.documents


class FailingAfterYieldConnector(FakeConnector):
    def iter_documents(self, tenant_id: str):
        yield from self.documents
        raise RuntimeError("vault unavailable")


def document(
    source_id: str = "50_Tech_AI自動化/Agent.md",
    revision: str = "rev-1",
    body: str = "# Agent\n\nAgent workflow",
) -> SourceDocument:
    return SourceDocument(
        tenant_id="kevin",
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title="Agent",
        body=body,
        cloud_key="ai",
        source_revision=revision,
        updated_at="2026-07-13T00:00:00+00:00",
        metadata={"concepts": ("AI Agents",)},
    )


@pytest.fixture
def portal_repo(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    return PortalRepository(path)


@pytest.fixture
def fake_connector():
    return FakeConnector([document()])


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


def test_reindexing_same_revision_is_idempotent(
    portal_repo, fake_connector, fake_embedder
):
    first = run_index("kevin", fake_connector, portal_repo, fake_embedder)
    second = run_index("kevin", fake_connector, portal_repo, fake_embedder)

    assert first.indexed == 1
    assert second.unchanged == 1
    assert len(portal_repo.list_items("kevin")) == 1
    assert len(fake_embedder.calls) == 1


def test_normalization_uses_first_body_paragraph_and_metadata():
    doc = document(body="# Heading\n\nFirst useful paragraph\n\nSecond paragraph")

    item = normalize_document(doc)

    assert item.summary == "First useful paragraph"
    assert item.item_type == "research"
    assert item.concepts == ("AI Agents",)


def test_index_persists_embeddings_and_successful_sync_run(portal_repo):
    embedder = FakeEmbedder()

    report = run_index(
        "kevin", FakeConnector([document()]), portal_repo, embedder
    )

    connection = portal_connect(portal_repo.path)
    try:
        chunk = connection.execute(
            """
            SELECT embedding_json, embedding_dimensions
            FROM knowledge_chunks
            WHERE tenant_id = ?
            """,
            ("kevin",),
        ).fetchone()
        sync = connection.execute(
            """
            SELECT status, indexed_count
            FROM sync_runs
            WHERE tenant_id = ?
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            ("kevin",),
        ).fetchone()
    finally:
        connection.close()

    assert report.indexed == 1
    assert json.loads(chunk["embedding_json"]) == [
        float(len(embedder.calls[0][0])),
        1.0,
    ]
    assert chunk["embedding_dimensions"] == 2
    assert embedder.calls[0][1] == "RETRIEVAL_DOCUMENT"
    assert dict(sync) == {"status": "success", "indexed_count": 1}


def test_successful_empty_scan_soft_deletes_missing_source_ids(portal_repo):
    embedder = FakeEmbedder()
    run_index("kevin", FakeConnector([document()]), portal_repo, embedder)

    report = run_index("kevin", FakeConnector([]), portal_repo, embedder)

    assert report.deleted == 1
    assert portal_repo.list_items("kevin") == []
    assert len(embedder.calls) == 1


def test_source_connector_protocol_requires_source_type():
    assert SourceConnector.__annotations__["source_type"] is str


def test_failed_scan_keeps_the_last_successful_projection(portal_repo):
    embedder = FakeEmbedder()
    run_index("kevin", FakeConnector([document()]), portal_repo, embedder)
    previous = portal_repo.list_items("kevin")
    changed = document(revision="rev-2", body="changed content")

    report = run_index(
        "kevin", FailingAfterYieldConnector([changed]), portal_repo, embedder
    )

    connection = portal_connect(portal_repo.path)
    try:
        latest_status = connection.execute(
            """
            SELECT status
            FROM sync_runs
            WHERE tenant_id = ?
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            ("kevin",),
        ).fetchone()["status"]
    finally:
        connection.close()

    assert report.failed == 1
    assert portal_repo.list_items("kevin") == previous
    assert latest_status == "stale"


def test_index_rejects_a_document_from_another_tenant(portal_repo):
    untrusted = replace(document(), tenant_id="attacker")

    report = run_index(
        "kevin", FakeConnector([untrusted]), portal_repo, FakeEmbedder()
    )

    assert report.failed == 1
    assert portal_repo.list_items("kevin") == []
    assert portal_repo.list_items("attacker") == []
    connection = portal_connect(portal_repo.path)
    try:
        diagnostic = connection.execute(
            """
            SELECT error_summary
            FROM sync_runs
            WHERE tenant_id = ?
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            ("kevin",),
        ).fetchone()["error_summary"]
    finally:
        connection.close()
    assert "tenant mismatch" in diagnostic
    assert len(diagnostic) <= 500


def test_embedding_write_failure_rolls_back_the_entire_projection(portal_repo):
    embedder = FakeEmbedder()
    retained = document(source_id="50_Tech_AI自動化/Retained.md")
    changing = document(source_id="50_Tech_AI自動化/Changing.md")
    run_index(
        "kevin", FakeConnector([retained, changing]), portal_repo, embedder
    )
    before = _projection_snapshot(portal_repo)
    connection = portal_connect(portal_repo.path)
    try:
        connection.executescript(
            """
            CREATE TRIGGER fail_embedding_persistence
            BEFORE UPDATE OF embedding_json ON knowledge_chunks
            WHEN NEW.embedding_json IS NOT NULL
            BEGIN
                SELECT RAISE(ABORT, 'forced embedding persistence failure');
            END;
            """
        )
    finally:
        connection.close()

    report = run_index(
        "kevin",
        FakeConnector(
            [
                document(
                    source_id="50_Tech_AI自動化/Changing.md",
                    revision="rev-2",
                    body="changed body",
                )
            ]
        ),
        portal_repo,
        embedder,
    )

    assert report == IndexReport(indexed=0, unchanged=0, deleted=0, failed=1)
    assert _projection_snapshot(portal_repo) == before
    connection = portal_connect(portal_repo.path)
    try:
        sync = connection.execute(
            """
            SELECT status, error_summary
            FROM sync_runs
            WHERE tenant_id = ?
            ORDER BY started_at DESC, run_id DESC
            LIMIT 1
            """,
            ("kevin",),
        ).fetchone()
    finally:
        connection.close()
    assert sync["status"] == "stale"
    assert "forced embedding persistence failure" in sync["error_summary"]


def _projection_snapshot(repo):
    items = repo.list_items("kevin")
    connection = portal_connect(repo.path)
    try:
        chunks = connection.execute(
            """
            SELECT tenant_id, source_id, chunk_index, chunk_text,
                   embedding_json, embedding_model, embedding_dimensions
            FROM knowledge_chunks
            WHERE tenant_id = ?
            ORDER BY source_id, chunk_index
            """,
            ("kevin",),
        ).fetchall()
    finally:
        connection.close()
    return items, [tuple(row) for row in chunks]
