import json
import logging

import pytest

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.indexer import run_index
from brain_portal.models import KnowledgeItem, SearchHit, SourceDocument
from brain_portal.search import SearchResults, hybrid_search


MODEL_ID = "models/gemini-embedding-001"


class FakeEmbedder:
    model_id = MODEL_ID
    dimensions = 2

    def __init__(self, vector=(1.0, 0.0)):
        self.vector = list(vector)
        self.calls = []

    def embed(self, text: str, task_type: str) -> list[float]:
        self.calls.append((text, task_type))
        return self.vector


class FailingEmbedder(FakeEmbedder):
    def embed(self, text: str, task_type: str) -> list[float]:
        raise RuntimeError("embedding unavailable")


def item(tenant_id: str, source_id: str, title: str, cloud_key="ai"):
    return KnowledgeItem(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title=title,
        summary=title,
        body=title,
        cloud_key=cloud_key,
        item_type="research",
        concepts=(),
        place=None,
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
    )


@pytest.fixture
def portal_repo(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    return PortalRepository(path)


def seed(repo, knowledge_item, chunk_text, vector, model_id=MODEL_ID):
    repo.upsert_item(
        knowledge_item.tenant_id, knowledge_item, chunks=[chunk_text]
    )
    connection = portal_connect(repo.path)
    try:
        with connection:
            connection.execute(
                """
                UPDATE knowledge_chunks
                SET embedding_json = ?, embedding_model = ?,
                    embedding_dimensions = ?
                WHERE tenant_id = ? AND source_id = ?
                """,
                (
                    json.dumps(vector),
                    model_id,
                    len(vector),
                    knowledge_item.tenant_id,
                    knowledge_item.source_id,
                ),
            )
    finally:
        connection.close()


def test_hybrid_search_filters_tenant_and_cloud_before_ranking(portal_repo):
    seed(portal_repo, item("tenant-a", "agent", "Agent workflow"), "agent workflow", [1.0, 0.0])
    seed(portal_repo, item("tenant-a", "food", "Food workflow", "food"), "agent workflow", [1.0, 0.0])
    seed(portal_repo, item("tenant-b", "secret", "B secret"), "agent workflow", [1.0, 0.0])
    embedder = FakeEmbedder()

    results = hybrid_search(portal_repo, embedder, "tenant-a", "agent workflow", "ai", 5)

    assert isinstance(results, SearchResults)
    assert isinstance(results.hits, tuple)
    assert results.degraded is False
    assert [hit.item.title for hit in results] == ["Agent workflow"]
    assert {hit.item.tenant_id for hit in results} == {"tenant-a"}
    assert embedder.calls == [("agent workflow", "RETRIEVAL_QUERY")]


def test_vector_candidates_do_not_mix_model_or_dimension_spaces(portal_repo):
    seed(portal_repo, item("kevin", "good", "Compatible"), "semantic", [0.8, 0.2])
    seed(portal_repo, item("kevin", "model", "Wrong model"), "semantic", [1.0, 0.0], "other-model")
    seed(portal_repo, item("kevin", "dims", "Wrong dimensions"), "semantic", [1.0, 0.0, 0.0])
    seed(portal_repo, item("kevin", "shape", "Wrong JSON shape"), "semantic", [1.0, 0.0])
    seed(portal_repo, item("kevin", "actual", "Wrong actual length"), "semantic", [1.0, 0.0, 0.0])
    seed(portal_repo, item("kevin", "finite", "Non-finite"), "semantic", [float("nan"), 0.0])
    connection = portal_connect(portal_repo.path)
    try:
        with connection:
            connection.execute(
                "UPDATE knowledge_chunks SET embedding_json = ? WHERE tenant_id = ? AND source_id = ?",
                ('{"bad": 1}', "kevin", "shape"),
            )
            connection.execute(
                "UPDATE knowledge_chunks SET embedding_dimensions = 2 WHERE tenant_id = ? AND source_id = ?",
                ("kevin", "actual"),
            )
    finally:
        connection.close()

    results = hybrid_search(portal_repo, FakeEmbedder(), "kevin", "no lexical match", None, 10)

    assert [hit.item.title for hit in results] == ["Compatible"]
    assert results[0].matched_by == ("semantic",)
    assert results.degraded is False


def test_rrf_uses_k_60_and_deduplicates_by_tenant_and_source():
    first = item("kevin", "first", "First")
    second = item("kevin", "second", "Second")

    class RankedRepo:
        def lexical_search(self, *args, **kwargs):
            return [SearchHit(first, 10.0, ("lexical",)), SearchHit(second, 9.0, ("lexical",))]

        def vector_search(self, *args, **kwargs):
            return [SearchHit(second, 1.0, ("semantic",)), SearchHit(first, 0.9, ("semantic",))]

    results = hybrid_search(RankedRepo(), FakeEmbedder(), "kevin", "query", None, 10)

    assert len(results) == 2
    assert {hit.item.source_id for hit in results} == {"first", "second"}
    assert all(hit.score == pytest.approx(1 / 61 + 1 / 62) for hit in results)
    assert all(hit.matched_by == ("lexical", "semantic") for hit in results)


def test_vector_failure_degrades_to_observable_lexical(portal_repo, caplog):
    seed(portal_repo, item("kevin", "claude", "Claude"), "Claude agent", [1.0, 0.0])

    with caplog.at_level(logging.WARNING):
        results = hybrid_search(portal_repo, FailingEmbedder(), "kevin", "Claude", None, 5)

    assert results[0].matched_by == ("lexical",)
    assert results.degraded is True
    assert "semantic retrieval degraded" in caplog.text
    assert "kevin" in caplog.text


@pytest.mark.parametrize(
    ("model_id", "dimensions"),
    [("", 2), (MODEL_ID, 0), (MODEL_ID, 3)],
)
def test_invalid_query_embedding_space_degrades_to_lexical(
    portal_repo, model_id, dimensions
):
    seed(portal_repo, item("kevin", "claude", "Claude"), "Claude agent", [1.0, 0.0])
    embedder = FakeEmbedder()
    embedder.model_id = model_id
    embedder.dimensions = dimensions

    results = hybrid_search(portal_repo, embedder, "kevin", "Claude", None, 5)

    assert results.degraded is True
    assert results[0].matched_by == ("lexical",)


def test_indexed_embedding_space_is_respected_by_hybrid_search(portal_repo):
    doc = SourceDocument(
        tenant_id="kevin",
        source_id="note.md",
        source_type="obsidian",
        canonical_ref="obsidian://note.md",
        title="Indexed note",
        body="semantic content",
        cloud_key="ai",
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
        metadata={},
    )

    class Connector:
        source_type = "obsidian"

        def iter_documents(self, tenant_id):
            yield doc

    index_embedder = FakeEmbedder()
    index_embedder.model_id = "index-model"
    run_index("kevin", Connector(), portal_repo, index_embedder)
    matching = FakeEmbedder()
    matching.model_id = "index-model"
    other = FakeEmbedder()
    other.model_id = "other-model"

    matching_results = hybrid_search(
        portal_repo, matching, "kevin", "unmatched query", None, 5
    )
    other_results = hybrid_search(
        portal_repo, other, "kevin", "unmatched query", None, 5
    )

    assert [hit.item.title for hit in matching_results] == ["Indexed note"]
    assert matching_results[0].matched_by == ("semantic",)
    assert other_results.hits == ()
