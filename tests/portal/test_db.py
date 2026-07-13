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
    repo.upsert_item(item("tenant-a", "same", "A only"), chunks=[])
    repo.upsert_item(item("tenant-b", "same", "B only"), chunks=[])

    assert [row.title for row in repo.list_items("tenant-a")] == ["A only"]
    assert [row.title for row in repo.list_items("tenant-b")] == ["B only"]


def test_upsert_replaces_only_the_matching_tenant_item(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    repo.upsert_item(item("tenant-a", "same", "A original"), chunks=[])
    repo.upsert_item(item("tenant-b", "same", "B original"), chunks=[])

    repo.upsert_item(item("tenant-a", "same", "A updated"), chunks=[])

    assert [row.title for row in repo.list_items("tenant-a")] == ["A updated"]
    assert [row.title for row in repo.list_items("tenant-b")] == ["B original"]
