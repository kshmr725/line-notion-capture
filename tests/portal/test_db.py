from dataclasses import replace

import pytest

from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.models import KnowledgeItem


def item(tenant_id: str, source_id: str, title: str) -> KnowledgeItem:
    return KnowledgeItem(
        tenant_id=tenant_id,
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title=title,
        summary=f"{title} summary",
        body="body",
        cloud_key="ai",
        item_type="research",
        concepts=("AI Agents",),
        place=None,
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
    )


def test_repository_never_returns_another_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item("tenant-a", item("tenant-a", "same", "A only"), chunks=[])
    repo.upsert_item("tenant-b", item("tenant-b", "same", "B only"), chunks=[])

    assert [row.title for row in repo.list_items("tenant-a")] == ["A only"]
    assert [row.title for row in repo.list_items("tenant-b")] == ["B only"]


def test_upsert_replaces_only_the_matching_tenant_item(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item(
        "tenant-a", item("tenant-a", "same", "A original"), chunks=[]
    )
    repo.upsert_item(
        "tenant-b", item("tenant-b", "same", "B original"), chunks=[]
    )

    repo.upsert_item(
        "tenant-a", item("tenant-a", "same", "A updated"), chunks=[]
    )

    assert [row.title for row in repo.list_items("tenant-a")] == ["A updated"]
    assert [row.title for row in repo.list_items("tenant-b")] == ["B original"]


def test_upsert_rejects_an_empty_trusted_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)

    with pytest.raises(ValueError, match="trusted tenant_id is required"):
        repo.upsert_item("", item("tenant-a", "same", "A only"), chunks=[])

    assert repo.list_items("tenant-a") == []


def test_upsert_rejects_an_item_from_another_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)

    with pytest.raises(ValueError, match="item tenant_id does not match"):
        repo.upsert_item(
            "tenant-a", item("tenant-b", "same", "B secret"), chunks=[]
        )

    assert repo.list_items("tenant-a") == []
    assert repo.list_items("tenant-b") == []


def test_fts_match_rank_and_relations_are_tenant_scoped(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    tenant_a_item = replace(
        item("tenant-a", "shared", "A result"),
        concepts=("A private concept",),
        place={"name": "A private place"},
    )
    tenant_b_item = replace(
        item("tenant-b", "shared", "B secret"),
        concepts=("B private concept",),
        place={"name": "B private place"},
    )
    repo.upsert_item(
        "tenant-a", tenant_a_item, chunks=["shared agent workflow"]
    )

    [before] = repo.lexical_search("tenant-a", "shared", limit=10)
    repo.upsert_item(
        "tenant-b", tenant_b_item, chunks=["shared shared secret workflow"]
    )
    [after] = repo.lexical_search("tenant-a", "shared", limit=10)

    assert before.item == after.item == tenant_a_item
    assert before.score == after.score
    assert repo.lexical_search("tenant-a", "secret", limit=10) == []
    assert [hit.item.title for hit in repo.lexical_search("tenant-b", "secret")] == [
        "B secret"
    ]
    assert repo.list_items("tenant-a")[0].concepts == ("A private concept",)
    assert repo.list_items("tenant-a")[0].place == {"name": "A private place"}
    assert repo.list_items("tenant-b")[0].concepts == ("B private concept",)
    assert repo.list_items("tenant-b")[0].place == {"name": "B private place"}
