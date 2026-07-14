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
class AuthenticatedPrincipal:
    user_id: str
    email: str


@dataclass(frozen=True)
class OnboardingState:
    tenant_id: str
    status: str


@dataclass(frozen=True)
class CloudProposal:
    key: str
    label: str
    confidence: float
    sample_titles: tuple[str, ...]
    detected_fields: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class DerivedView:
    kind: str
    cloud_key: str
    columns: tuple[str, ...]
    filters: tuple[tuple[str, str], ...]
    sort: str | None = None


@dataclass(frozen=True)
class TableRow:
    source_id: str
    title: str
    url: str
    updated_at: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class DerivedTable:
    view: DerivedView
    column_labels: tuple[str, ...]
    rows: tuple[TableRow, ...]


@dataclass(frozen=True)
class ChartSpec:
    chart_type: str
    title: str
    axis_label: str
    labels: tuple[str, ...]
    values: tuple[float, ...]
    summary: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class SyncRun:
    source_type: str
    status: str
    finished_at: str | None


@dataclass(frozen=True)
class CitedAnswer:
    text: str
    source_ids: tuple[str, ...]
    provider: str
    degraded: bool = False

    def __post_init__(self) -> None:
        if not self.source_ids:
            raise ValueError("at least one source_id is required")
