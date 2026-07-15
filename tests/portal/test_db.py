from dataclasses import replace

import pytest

from brain_portal.db import PortalRepository, init_portal_db, portal_connect
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


def test_get_item_returns_the_matching_tenant_item(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item("tenant-a", item("tenant-a", "page-1", "A note"), chunks=[])
    repo.upsert_item("tenant-b", item("tenant-b", "page-1", "B note"), chunks=[])

    assert repo.get_item("tenant-a", "page-1").title == "A note"
    assert repo.get_item("tenant-b", "page-1").title == "B note"


def test_get_item_returns_none_when_missing_or_wrong_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item("tenant-a", item("tenant-a", "page-1", "A note"), chunks=[])

    assert repo.get_item("tenant-a", "missing") is None
    assert repo.get_item("tenant-b", "page-1") is None


def test_list_cloud_labels_is_ordered_and_tenant_scoped(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    connection = portal_connect(path)
    with connection:
        connection.executemany(
            "INSERT INTO tenants (tenant_id, display_name) VALUES (?, ?)",
            (("tenant-a", "A"), ("tenant-b", "B")),
        )
        connection.executemany(
            "INSERT INTO tenant_clouds (tenant_id, cloud_key, label) VALUES (?, ?, ?)",
            (
                ("tenant-a", "z-notes", "Z Notes"),
                ("tenant-a", "research", "研究資料"),
                ("tenant-b", "private", "Private Cloud"),
            ),
        )
    connection.close()

    assert repo.list_cloud_labels("tenant-a") == {
        "research": "研究資料",
        "z-notes": "Z Notes",
    }


def _record_sync_run(
    path, tenant_id: str, run_id: str, source_type: str, status: str, finished_at: str
) -> None:
    connection = portal_connect(path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO tenants (tenant_id, display_name)
                VALUES (?, ?)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tenant_id, tenant_id),
            )
            connection.execute(
                """
                INSERT INTO sync_runs (
                    tenant_id, run_id, source_type, status, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, run_id, source_type, status, finished_at, finished_at),
            )
    finally:
        connection.close()


def test_latest_sync_returns_the_most_recent_finished_run_for_a_source_type(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    _record_sync_run(
        path, "kevin", "run-1", "notion", "success", "2026-07-13T10:00:00+00:00"
    )
    _record_sync_run(
        path, "kevin", "run-2", "notion", "stale", "2026-07-13T11:00:00+00:00"
    )
    _record_sync_run(
        path, "kevin", "run-3", "obsidian", "success", "2026-07-13T12:00:00+00:00"
    )

    sync = repo.latest_sync("kevin", "notion")

    assert sync.status == "stale"
    assert sync.source_type == "notion"


def test_latest_sync_ignores_other_tenants_and_missing_runs(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    _record_sync_run(
        path, "other-tenant", "run-1", "notion", "success", "2026-07-13T10:00:00+00:00"
    )

    assert repo.latest_sync("kevin", "notion") is None
