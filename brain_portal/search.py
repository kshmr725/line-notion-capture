from __future__ import annotations

import logging

from brain_portal.db import PortalRepository
from brain_portal.indexer import EmbeddingProvider
from brain_portal.models import SearchHit


LOGGER = logging.getLogger(__name__)
RRF_K = 60


def hybrid_search(
    repo: PortalRepository,
    embedder: EmbeddingProvider,
    tenant_id: str,
    query: str,
    cloud_key: str | None,
    limit: int = 10,
) -> list[SearchHit]:
    if not tenant_id.strip() or not query.strip() or limit <= 0:
        return []
    lexical = repo.lexical_search(
        tenant_id,
        query,
        limit=limit,
        cloud_key=cloud_key,
    )
    semantic = []
    try:
        query_vector = [
            float(value) for value in embedder.embed(query, "RETRIEVAL_QUERY")
        ]
        semantic = repo.vector_search(
            tenant_id,
            query_vector,
            model_id=str(
                getattr(embedder, "model_id", type(embedder).__name__)
            ),
            dimensions=len(query_vector),
            limit=limit,
            cloud_key=cloud_key,
        )
    except Exception as error:
        LOGGER.warning(
            "semantic retrieval degraded for tenant=%s error=%s",
            tenant_id,
            type(error).__name__,
        )

    fused: dict[tuple[str, str], dict[str, object]] = {}
    _add_ranking(fused, lexical, "lexical")
    _add_ranking(fused, semantic, "semantic")
    results = []
    for value in fused.values():
        matched = value["matched"]
        results.append(
            SearchHit(
                item=value["item"],
                score=value["score"],
                matched_by=tuple(
                    method
                    for method in ("lexical", "semantic")
                    if method in matched
                ),
            )
        )
    return sorted(
        results,
        key=lambda hit: (-hit.score, hit.item.source_id),
    )[:limit]


def _add_ranking(
    fused: dict[tuple[str, str], dict[str, object]],
    ranking: list[SearchHit],
    method: str,
) -> None:
    for rank, hit in enumerate(ranking, start=1):
        key = (hit.item.tenant_id, hit.item.source_id)
        value = fused.setdefault(
            key,
            {"item": hit.item, "score": 0.0, "matched": set()},
        )
        value["score"] += 1 / (RRF_K + rank)
        value["matched"].add(method)
