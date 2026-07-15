from __future__ import annotations

from types import SimpleNamespace

from brain_portal.models import SourceDocument
from shared_portal import create_shared_portal


class FakeConnector:
    source_type = "notion"

    def iter_documents(self, tenant_id):
        yield SourceDocument(
            tenant_id=tenant_id,
            source_id="page-1",
            source_type="notion",
            canonical_ref="https://notion.so/page-1",
            title="使用者資料庫",
            body="這是可以搜尋的 Second Brain 資料。",
            cloud_key="ai",
            source_revision="rev-1",
            updated_at="2026-07-15T00:00:00Z",
            metadata={"summary": "共用 Notion 資料"},
        )


def test_shared_portal_uses_existing_notion_configuration(tmp_path):
    settings = SimpleNamespace(
        notion_token="existing-token",
        notion_database_id="existing-database",
        gemini_api_key="",
        deepseek_api_key="",
    )
    portal = create_shared_portal(
        settings,
        database_path=str(tmp_path / "shared.sqlite3"),
        connector_factory=lambda **kwargs: FakeConnector(),
    )

    response = portal.test_client().get("/")

    assert response.status_code == 200
    assert "使用者資料庫" in response.get_data(as_text=True)
    assert portal.extensions["shared_portal_sync"]["status"] == "ready"


def test_shared_portal_fails_readably_when_existing_notion_is_missing(tmp_path):
    settings = SimpleNamespace(
        notion_token="",
        notion_database_id="",
        gemini_api_key="",
        deepseek_api_key="",
    )
    portal = create_shared_portal(settings, database_path=str(tmp_path / "shared.sqlite3"))

    response = portal.test_client().get("/")

    assert response.status_code == 503
    assert "Notion 尚未連接" in response.get_data(as_text=True)
