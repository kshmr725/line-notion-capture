from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    display_name: str


@dataclass(frozen=True)
class SourceDocument:
    tenant_id: str
    source_id: str
    source_type: str
    canonical_ref: str
    title: str
    body: str
    cloud_key: str
    source_revision: str
    updated_at: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class KnowledgeItem:
    tenant_id: str
    source_id: str
    source_type: str
    canonical_ref: str
    title: str
    summary: str
    body: str
    cloud_key: str
    item_type: str
    concepts: tuple[str, ...]
    place: dict[str, object] | None
    source_revision: str
    updated_at: str


@dataclass(frozen=True)
class SearchHit:
    item: KnowledgeItem
    score: float
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class CitedAnswer:
    text: str
    source_ids: tuple[str, ...]
    provider: str
    degraded: bool = False
