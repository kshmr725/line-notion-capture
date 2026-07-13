import json
import logging

import pytest

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.models import KnowledgeItem, SearchHit
from brain_portal.search import hybrid_search


MODEL_ID = "models/gemini-embedding-001"


class FakeEmbedder:
    model_id = MODEL_ID

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

    hits = hybrid_search(portal_repo, embedder, "tenant-a", "agent workflow", "ai", 5)

    assert [hit.item.title for hit in hits] == ["Agent workflow"]
    assert {hit.item.tenant_id for hit in hits} == {"tenant-a"}
    assert embedder.calls == [("agent workflow", "RETRIEVAL_QUERY")]


def test_vector_candidates_do_not_mix_model_or_dimension_spaces(portal_repo):
    seed(portal_repo, item("kevin", "good", "Compatible"), "semantic", [0.8, 0.2])
    seed(portal_repo, item("kevin", "model", "Wrong model"), "semantic", [1.0, 0.0], "other-model")
    seed(portal_repo, item("kevin", "dims", "Wrong dimensions"), "semantic", [1.0, 0.0, 0.0])

    hits = hybrid_search(portal_repo, FakeEmbedder(), "kevin", "no lexical match", None, 10)

    assert [hit.item.title for hit in hits] == ["Compatible"]
    assert hits[0].matched_by == ("semantic",)


def test_rrf_uses_k_60_and_deduplicates_by_tenant_and_source():
    first = item("kevin", "first", "First")
    second = item("kevin", "second", "Second")

    class RankedRepo:
        def lexical_search(self, *args, **kwargs):
            return [SearchHit(first, 10.0, ("lexical",)), SearchHit(second, 9.0, ("lexical",))]

        def vector_search(self, *args, **kwargs):
            return [SearchHit(second, 1.0, ("semantic",)), SearchHit(first, 0.9, ("semantic",))]

    hits = hybrid_search(RankedRepo(), FakeEmbedder(), "kevin", "query", None, 10)

    assert len(hits) == 2
    assert {hit.item.source_id for hit in hits} == {"first", "second"}
    assert all(hit.score == pytest.approx(1 / 61 + 1 / 62) for hit in hits)
    assert all(hit.matched_by == ("lexical", "semantic") for hit in hits)


def test_vector_failure_degrades_to_observable_lexical(portal_repo, caplog):
    seed(portal_repo, item("kevin", "claude", "Claude"), "Claude agent", [1.0, 0.0])

    with caplog.at_level(logging.WARNING):
        hits = hybrid_search(portal_repo, FailingEmbedder(), "kevin", "Claude", None, 5)

    assert hits[0].matched_by == ("lexical",)
    assert "semantic retrieval degraded" in caplog.text
    assert "kevin" in caplog.text
