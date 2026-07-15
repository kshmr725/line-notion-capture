from __future__ import annotations

import pytest

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
from brain_portal.models import SourceDocument
from brain_portal.onboarding import (
    confirm_clouds,
    load_proposal,
    propose_clouds,
    revise_proposal,
    store_proposal,
)
from brain_portal.models import CloudEdit


class FakeEmbedder:
    model_id = "fake-embedding"
    dimensions = 2

    def embed(self, text: str, task_type: str) -> list[float]:
        return [float(len(text)), 1.0]


class FailingEmbedder:
    model_id = "fake-embedding"
    dimensions = 2

    def embed(self, text: str, task_type: str) -> list[float]:
        raise RuntimeError("provider unavailable")


def _doc(
    source_id: str,
    title: str,
    cloud_key: str = "",
    concepts: tuple[str, ...] = (),
    place: dict | None = None,
    tenant_id: str = "tenant-1",
    source_type: str = "notion",
) -> SourceDocument:
    return SourceDocument(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type=source_type,
        canonical_ref=f"https://www.notion.so/{source_id}",
        title=title,
        body=f"{title} body",
        cloud_key=cloud_key,
        source_revision="rev-1",
        updated_at="2026-07-14T00:00:00+00:00",
        metadata={"concepts": concepts, "place": place, "summary": f"{title} summary"},
    )


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    connection = portal_connect(path)
    with connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, display_name) VALUES ('tenant-1', 'Tenant One')"
        )
    connection.close()
    return repo


def test_propose_clouds_is_deterministic_for_the_same_documents():
    documents = (
        _doc("a", "Restaking Thesis", cloud_key="web3"),
        _doc("b", "Quiet Noodle Shop", cloud_key="food"),
    )

    first = propose_clouds(documents)
    second = propose_clouds(documents)

    assert first == second


def test_propose_clouds_groups_by_existing_cloud_key():
    documents = (
        _doc("a", "Restaking Thesis", cloud_key="web3"),
        _doc("b", "Another Web3 Note", cloud_key="web3"),
        _doc("c", "Quiet Noodle Shop", cloud_key="food"),
    )

    proposal = propose_clouds(documents)
    by_key = {group.key: group for group in proposal}

    assert by_key["web3"].source_ids == ("a", "b")
    assert by_key["web3"].confidence == 1.0
    assert by_key["food"].source_ids == ("c",)
    assert "ai" not in by_key


def test_propose_clouds_marks_unmapped_documents_as_a_low_confidence_group():
    documents = (
        _doc("a", "Mystery Note", cloud_key=""),
        _doc("b", "Another Mystery", cloud_key="not-a-real-cloud"),
    )

    [group] = propose_clouds(documents)

    assert group.key == "unmapped"
    assert group.confidence == 0.0
    assert set(group.source_ids) == {"a", "b"}


def test_propose_clouds_detects_concepts_and_place_fields():
    documents = (
        _doc("a", "Note", cloud_key="web3", concepts=("restaking",)),
        _doc("b", "Place", cloud_key="food", place={"name": "Cafe"}),
    )

    proposal = propose_clouds(documents)
    by_key = {group.key: group for group in proposal}

    assert "concepts" in by_key["web3"].detected_fields
    assert "place" in by_key["food"].detected_fields
    assert "summary" in by_key["web3"].detected_fields


def test_propose_clouds_never_mutates_input_documents():
    original = _doc("a", "Restaking Thesis", cloud_key="web3")
    documents = (original,)

    propose_clouds(documents)

    assert documents[0] is original
    assert documents[0].cloud_key == "web3"


def test_revise_proposal_can_merge_split_and_exclude_without_mutating_source_groups():
    proposal = propose_clouds(
        (
            _doc("a", "Restaking Thesis", cloud_key="web3"),
            _doc("b", "Quiet Noodle Shop", cloud_key="food"),
            _doc("c", "Agent Guide", cloud_key="ai"),
        )
    )

    revised = revise_proposal(
        proposal,
        {
            "a": CloudEdit(target_key="research", label="研究資料"),
            "b": CloudEdit(target_key="research", label="研究資料"),
            "c": CloudEdit(excluded=True),
            "foreign": CloudEdit(target_key="ignored", label="Ignored"),
        },
    )

    assert len(revised) == 1
    [group] = revised
    assert group.key == "research"
    assert group.label == "研究資料"
    assert group.source_ids == ("a", "b")
    assert proposal[0].source_ids == ("a",)


def test_store_and_load_proposal_round_trips(repository):
    documents = (_doc("a", "Restaking Thesis", cloud_key="web3"),)
    proposal = propose_clouds(documents)

    proposal_id = store_proposal(repository, "tenant-1", proposal)
    loaded = load_proposal(repository, "tenant-1", proposal_id)

    assert loaded == proposal


def test_store_proposal_sets_onboarding_status_to_proposed(repository):
    proposal = propose_clouds((_doc("a", "Note", cloud_key="ai"),))

    store_proposal(repository, "tenant-1", proposal)

    connection = portal_connect(repository.path)
    status = connection.execute(
        "SELECT onboarding_status FROM tenants WHERE tenant_id = 'tenant-1'"
    ).fetchone()["onboarding_status"]
    connection.close()
    assert status == "proposed"


def test_load_proposal_returns_none_for_an_unknown_id(repository):
    assert load_proposal(repository, "tenant-1", "not-a-real-id") is None


def test_load_proposal_never_returns_another_tenants_proposal(repository):
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, display_name) VALUES ('tenant-2', 'Tenant Two')"
        )
    connection.close()
    proposal = propose_clouds((_doc("a", "Note", cloud_key="ai"),))
    proposal_id = store_proposal(repository, "tenant-1", proposal)

    assert load_proposal(repository, "tenant-2", proposal_id) is None


def test_confirm_clouds_applies_accepted_mapping_and_indexes(repository):
    documents = (
        _doc("a", "Mystery Note", cloud_key="", tenant_id="tenant-1"),
        _doc("b", "Web3 Note", cloud_key="web3", tenant_id="tenant-1"),
    )
    proposal = propose_clouds(documents)
    proposal_id = store_proposal(repository, "tenant-1", proposal)

    state = confirm_clouds(
        repository,
        "tenant-1",
        proposal_id,
        {"unmapped": "food"},
        documents,
        FakeEmbedder(),
    )

    assert state.status == "ready"
    items = {item.source_id: item for item in repository.list_items("tenant-1")}
    assert items["a"].cloud_key == "food"
    assert items["b"].cloud_key == "web3"


def test_confirm_clouds_defaults_unmapped_groups_to_ai_when_not_overridden(repository):
    documents = (_doc("a", "Mystery Note", cloud_key=""),)
    proposal = propose_clouds(documents)
    proposal_id = store_proposal(repository, "tenant-1", proposal)

    confirm_clouds(repository, "tenant-1", proposal_id, {}, documents, FakeEmbedder())

    item = repository.list_items("tenant-1")[0]
    assert item.cloud_key == "ai"


def test_confirm_clouds_rejects_an_unknown_proposal(repository):
    with pytest.raises(ValueError):
        confirm_clouds(
            repository, "tenant-1", "not-a-real-id", {}, (), FakeEmbedder()
        )


def test_confirm_clouds_sets_status_confirmed_not_ready_on_indexing_failure(repository):
    documents = (_doc("a", "Note", cloud_key="ai"),)
    proposal = propose_clouds(documents)
    proposal_id = store_proposal(repository, "tenant-1", proposal)

    state = confirm_clouds(
        repository, "tenant-1", proposal_id, {}, documents, FailingEmbedder()
    )

    assert state.status == "confirmed"


def test_confirm_clouds_never_writes_to_another_tenant(repository):
    connection = portal_connect(repository.path)
    with connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, display_name) VALUES ('tenant-2', 'Tenant Two')"
        )
    connection.close()
    documents = (_doc("a", "Note", cloud_key="ai", tenant_id="tenant-1"),)
    proposal = propose_clouds(documents)
    proposal_id = store_proposal(repository, "tenant-1", proposal)

    confirm_clouds(repository, "tenant-1", proposal_id, {}, documents, FakeEmbedder())

    assert repository.list_items("tenant-2") == []
