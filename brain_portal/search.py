from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterator, Union

from brain_portal.db import PortalRepository
from brain_portal.indexer import EmbeddingProvider
from brain_portal.models import SearchHit


LOGGER = logging.getLogger(__name__)
RRF_K = 60


@dataclass(frozen=True)
class SearchResults:
    hits: tuple[SearchHit, ...]
    degraded: bool = False

    def __iter__(self) -> Iterator[SearchHit]:
        return iter(self.hits)

    def __len__(self) -> int:
        return len(self.hits)

    def __getitem__(self, index: Union[int, slice]):
        return self.hits[index]


def hybrid_search(
    repo: PortalRepository,
    embedder: EmbeddingProvider,
    tenant_id: str,
    query: str,
    cloud_key: str | None,
    limit: int = 10,
) -> SearchResults:
    if not tenant_id.strip() or not query.strip() or limit <= 0:
        return SearchResults(hits=())
    lexical = repo.lexical_search(
        tenant_id,
        query,
        limit=limit,
        cloud_key=cloud_key,
    )
    semantic = []
    degraded = False
    try:
        model_id = embedder.model_id.strip()
        dimensions = embedder.dimensions
        if not model_id or not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("embedding provider space is invalid")
        query_vector = [
            float(value) for value in embedder.embed(query, "RETRIEVAL_QUERY")
        ]
        if len(query_vector) != dimensions or not all(
            math.isfinite(value) for value in query_vector
        ):
            raise ValueError("query embedding does not match provider space")
        semantic = repo.vector_search(
            tenant_id,
            query_vector,
            model_id=model_id,
            dimensions=dimensions,
            limit=limit,
            cloud_key=cloud_key,
        )
    except Exception as error:
        degraded = True
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
    return SearchResults(
        hits=tuple(
            sorted(
                results,
                key=lambda hit: (-hit.score, hit.item.source_id),
            )[:limit]
        ),
        degraded=degraded,
    )


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
