from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from brain_portal.db import PortalRepository, portal_connect
from brain_portal.indexer import EmbeddingProvider, run_index
from brain_portal.models import CloudEdit, CloudProposal, OnboardingState, SourceDocument


CANONICAL_CLOUDS = {
    "web3": "Web3 商業研究",
    "food": "美食與咖啡地圖",
    "ai": "AI 自動化",
}

Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def propose_clouds(documents: Sequence[SourceDocument]) -> tuple[CloudProposal, ...]:
    groups: dict[str, list[SourceDocument]] = {}
    for doc in documents:
        key = doc.cloud_key.strip() if doc.cloud_key.strip() in CANONICAL_CLOUDS else "unmapped"
        groups.setdefault(key, []).append(doc)

    proposals = []
    for key in (*CANONICAL_CLOUDS.keys(), "unmapped"):
        docs = groups.get(key)
        if not docs:
            continue
        proposals.append(
            CloudProposal(
                key=key,
                label=CANONICAL_CLOUDS.get(key, "未分類"),
                confidence=1.0 if key != "unmapped" else 0.0,
                sample_titles=tuple(doc.title for doc in docs[:3]),
                detected_fields=_detected_fields(docs),
                source_ids=tuple(doc.source_id for doc in docs),
            )
        )
    return tuple(proposals)


def _detected_fields(docs: Sequence[SourceDocument]) -> tuple[str, ...]:
    fields = set()
    for doc in docs:
        if doc.metadata.get("concepts"):
            fields.add("concepts")
        if doc.metadata.get("place"):
            fields.add("place")
        if doc.metadata.get("summary"):
            fields.add("summary")
    return tuple(sorted(fields))


def revise_proposal(
    proposal: Sequence[CloudProposal], edits: Mapping[str, CloudEdit]
) -> tuple[CloudProposal, ...]:
    """Apply source-level proposal edits without changing sources or the stored proposal."""
    source_groups = {
        source_id: group
        for group in proposal
        for source_id in group.source_ids
    }
    grouped: dict[tuple[str, str], list[str]] = {}
    for source_id, original in source_groups.items():
        edit = edits.get(source_id, CloudEdit())
        if edit.excluded:
            continue
        key = _safe_cloud_key(edit.target_key or original.key)
        label = (edit.label or CANONICAL_CLOUDS.get(key) or original.label).strip()
        grouped.setdefault((key, label), []).append(source_id)
    return tuple(
        CloudProposal(
            key=key,
            label=label,
            confidence=1.0,
            sample_titles=(),
            detected_fields=(),
            source_ids=tuple(source_ids),
        )
        for (key, label), source_ids in grouped.items()
    )


def _safe_cloud_key(value: str) -> str:
    candidate = "".join(
        char.lower() if char.isascii() and char.isalnum() else "-" for char in value.strip()
    ).strip("-")
    return candidate[:40] or "unmapped"


def store_proposal(
    repository: PortalRepository,
    tenant_id: str,
    proposal: tuple[CloudProposal, ...],
    clock: Clock | None = None,
) -> str:
    clock = clock or _default_clock
    proposal_id = secrets.token_urlsafe(16)
    payload = json.dumps(
        [
            {
                "key": group.key,
                "label": group.label,
                "confidence": group.confidence,
                "sample_titles": list(group.sample_titles),
                "detected_fields": list(group.detected_fields),
                "source_ids": list(group.source_ids),
            }
            for group in proposal
        ]
    )
    connection = portal_connect(repository.path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO cloud_proposals (tenant_id, proposal_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, proposal_id, payload, clock().isoformat()),
            )
            connection.execute(
                "UPDATE tenants SET onboarding_status = 'proposed' WHERE tenant_id = ?",
                (tenant_id,),
            )
    finally:
        connection.close()
    return proposal_id


def load_proposal(
    repository: PortalRepository, tenant_id: str, proposal_id: str
) -> tuple[CloudProposal, ...] | None:
    connection = portal_connect(repository.path)
    try:
        row = connection.execute(
            """
            SELECT payload_json FROM cloud_proposals
            WHERE tenant_id = ? AND proposal_id = ?
            """,
            (tenant_id, proposal_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return tuple(
        CloudProposal(
            key=entry["key"],
            label=entry["label"],
            confidence=entry["confidence"],
            sample_titles=tuple(entry["sample_titles"]),
            detected_fields=tuple(entry["detected_fields"]),
            source_ids=tuple(entry["source_ids"]),
        )
        for entry in json.loads(row["payload_json"])
    )


def confirm_clouds(
    repository: PortalRepository,
    tenant_id: str,
    proposal_id: str,
    accepted: Mapping[str, str],
    documents: Sequence[SourceDocument],
    embedder: EmbeddingProvider | None,
    *,
    edits: Mapping[str, CloudEdit] | None = None,
) -> OnboardingState:
    proposal = load_proposal(repository, tenant_id, proposal_id)
    if proposal is None:
        raise ValueError("unknown Cloud proposal")

    if edits is None:
        remap = _accepted_remap(proposal, accepted)
        cloud_labels = {
            key: CANONICAL_CLOUDS.get(key, key)
            for key in set(remap.values())
        }
    else:
        revised = revise_proposal(proposal, edits)
        remap = {
            source_id: group.key
            for group in revised
            for source_id in group.source_ids
        }
        cloud_labels = {group.key: group.label for group in revised}
    remapped_documents = tuple(
        replace(doc, cloud_key=remap.get(doc.source_id, doc.cloud_key))
        for doc in documents
        if doc.tenant_id == tenant_id and doc.source_id in remap
    )

    _set_onboarding_status(repository, tenant_id, "confirmed")
    _store_cloud_labels(repository, tenant_id, cloud_labels)
    if not remapped_documents:
        _set_onboarding_status(repository, tenant_id, "ready")
        return OnboardingState(tenant_id=tenant_id, status="ready")
    source_type = remapped_documents[0].source_type if remapped_documents else "notion"
    connector = _StaticConnector(source_type=source_type, documents=remapped_documents)
    report = run_index(tenant_id, connector, repository, embedder)
    status = "ready" if report.failed == 0 else "confirmed"
    _set_onboarding_status(repository, tenant_id, status)
    return OnboardingState(tenant_id=tenant_id, status=status)


def _accepted_remap(
    proposal: Sequence[CloudProposal], accepted: Mapping[str, str]
) -> dict[str, str]:
    remap: dict[str, str] = {}
    for group in proposal:
        final_key = accepted.get(group.key, group.key)
        if final_key not in CANONICAL_CLOUDS:
            final_key = "ai"
        for source_id in group.source_ids:
            remap[source_id] = final_key
    return remap


def _store_cloud_labels(
    repository: PortalRepository, tenant_id: str, cloud_labels: Mapping[str, str]
) -> None:
    connection = portal_connect(repository.path)
    try:
        with connection:
            for cloud_key, label in cloud_labels.items():
                connection.execute(
                    """
                    INSERT INTO tenant_clouds (tenant_id, cloud_key, label)
                    VALUES (?, ?, ?)
                    ON CONFLICT (tenant_id, cloud_key) DO UPDATE SET label = excluded.label
                    """,
                    (tenant_id, cloud_key, label),
                )
    finally:
        connection.close()


def _set_onboarding_status(repository: PortalRepository, tenant_id: str, status: str) -> None:
    connection = portal_connect(repository.path)
    try:
        with connection:
            connection.execute(
                "UPDATE tenants SET onboarding_status = ? WHERE tenant_id = ?",
                (status, tenant_id),
            )
    finally:
        connection.close()


@dataclass(frozen=True)
class _StaticConnector:
    source_type: str
    documents: tuple[SourceDocument, ...]

    def iter_documents(self, tenant_id: str):
        return iter(doc for doc in self.documents if doc.tenant_id == tenant_id)
