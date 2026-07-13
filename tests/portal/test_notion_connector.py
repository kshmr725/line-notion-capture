from __future__ import annotations

import pytest

from brain_portal.connectors.notion import NotionConnector


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self.payload


def page(
    page_id: str = "example-page-id",
    title: str = "Claude Code",
    summary: str = "A guided summary.",
    cloud: str | None = "AI Automation",
    concepts: tuple[str, ...] = ("agents", "reliability"),
    revision: str = "2026-07-13T12:00:00.000Z",
    extra_properties: dict | None = None,
) -> dict:
    properties = {
        "title": {"type": "title", "title": [{"plain_text": title}]},
        "Summary": {"type": "rich_text", "rich_text": [{"plain_text": summary}]},
        "Concepts": {
            "type": "multi_select",
            "multi_select": [{"name": value} for value in concepts],
        },
    }
    if cloud is not None:
        properties["Cloud"] = {"type": "select", "select": {"name": cloud}}
    else:
        properties["Cloud"] = {"type": "select", "select": None}
    if extra_properties:
        properties.update(extra_properties)
    return {
        "id": page_id,
        "url": f"https://www.notion.so/{page_id}",
        "last_edited_time": revision,
        "properties": properties,
    }


def database_page(
    results: list[dict], has_more: bool = False, next_cursor: str | None = None
) -> dict:
    return {"results": results, "has_more": has_more, "next_cursor": next_cursor}


def blocks_page(
    texts: list[str], has_more: bool = False, next_cursor: str | None = None
) -> dict:
    return {
        "results": [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}
            for text in texts
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


class FakeTransport:
    def __init__(self, database_pages=None, block_pages=None, page_payload=None):
        self.database_pages = list(database_pages or [])
        self.block_pages = list(block_pages or [])
        self.page_payload = page_payload
        self.requests: list[tuple[str, str, dict]] = []

    def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return FakeResponse(200, self.database_pages.pop(0))

    def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        if url.endswith("/children"):
            return FakeResponse(200, self.block_pages.pop(0))
        return FakeResponse(200, self.page_payload)


@pytest.fixture
def transport(monkeypatch):
    fake = FakeTransport(
        database_pages=[database_page([page()])],
        block_pages=[blocks_page(["Agent workflow notes."])],
    )
    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake.post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake.get)
    return fake


@pytest.fixture
def notion_connector(transport):
    return NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )


def test_notion_item_exposes_direct_page_edit_url(notion_connector):
    [doc] = list(notion_connector.iter_documents("tenant-notion"))
    assert doc.canonical_ref == "https://www.notion.so/example-page-id"


def test_notion_item_maps_guided_fields(notion_connector):
    [doc] = list(notion_connector.iter_documents("tenant-notion"))

    assert doc.tenant_id == "tenant-notion"
    assert doc.source_id == "example-page-id"
    assert doc.source_type == "notion"
    assert doc.title == "Claude Code"
    assert doc.cloud_key == "ai"
    assert doc.metadata["summary"] == "A guided summary."
    assert doc.metadata["concepts"] == ("agents", "reliability")
    assert doc.body == "Agent workflow notes."
    assert doc.source_revision == "2026-07-13T12:00:00.000Z"


def test_notion_requests_carry_bearer_token_and_api_version(notion_connector, transport):
    list(notion_connector.iter_documents("tenant-notion"))

    for _, _, kwargs in transport.requests:
        assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
        assert kwargs["headers"]["Notion-Version"] == "2026-03-11"
        assert kwargs["timeout"] == 20


def test_notion_connector_never_writes(notion_connector, monkeypatch):
    calls = []
    for method in ("put", "patch", "delete"):
        monkeypatch.setattr(
            f"brain_portal.connectors.notion.requests.{method}",
            lambda *a, **k: calls.append(1),
            raising=False,
        )

    list(notion_connector.iter_documents("tenant-notion"))

    assert calls == []


@pytest.mark.parametrize(
    ("cloud_name", "expected_key"),
    [("AI Automation", "ai"), ("Web3 Research", "web3"), ("Food and Places", "food"), (None, "")],
)
def test_notion_cloud_select_maps_to_known_keys(monkeypatch, cloud_name, expected_key):
    fake = FakeTransport(
        database_pages=[database_page([page(cloud=cloud_name)])],
        block_pages=[blocks_page(["Body text."])],
    )
    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake.post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake.get)
    connector = NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )

    [doc] = list(connector.iter_documents("tenant-notion"))

    assert doc.cloud_key == expected_key


def test_notion_connector_paginates_the_database_query(monkeypatch):
    fake = FakeTransport(
        database_pages=[
            database_page([page("page-1")], has_more=True, next_cursor="cursor-1"),
            database_page([page("page-2")], has_more=False),
        ],
        block_pages=[blocks_page(["Body one."]), blocks_page(["Body two."])],
    )
    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake.post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake.get)
    connector = NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )

    docs = list(connector.iter_documents("tenant-notion"))

    assert [doc.source_id for doc in docs] == ["page-1", "page-2"]
    post_requests = [kwargs for method, _, kwargs in fake.requests if method == "POST"]
    assert post_requests[1]["json"]["start_cursor"] == "cursor-1"


def test_notion_connector_raises_permission_error_on_403(monkeypatch):
    fake = FakeTransport(database_pages=[])

    def denied_post(url, **kwargs):
        return FakeResponse(403, {"message": "restricted"})

    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", denied_post)
    connector = NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )

    with pytest.raises(PermissionError):
        list(connector.iter_documents("tenant-notion"))


def test_fetch_document_retrieves_a_single_page_without_a_database_query(monkeypatch):
    fake = FakeTransport(
        block_pages=[blocks_page(["Retrieved body."])],
        page_payload=page("example-page-id"),
    )
    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake.post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake.get)
    connector = NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )

    doc = connector.fetch_document("tenant-notion", "example-page-id")

    assert doc.canonical_ref == "https://www.notion.so/example-page-id"
    assert doc.body == "Retrieved body."
    assert not any(method == "POST" for method, _, _ in fake.requests)


def test_notion_connector_hides_unapproved_system_properties(monkeypatch):
    fake = FakeTransport(
        database_pages=[
            database_page(
                [
                    page(
                        extra_properties={
                            "Internal Sync Hash": {
                                "type": "rich_text",
                                "rich_text": [{"plain_text": "SECRET_HASH"}],
                            }
                        }
                    )
                ]
            )
        ],
        block_pages=[blocks_page(["Body text."])],
    )
    monkeypatch.setattr("brain_portal.connectors.notion.requests.post", fake.post)
    monkeypatch.setattr("brain_portal.connectors.notion.requests.get", fake.get)
    connector = NotionConnector(
        token="secret-token", database_id="db-1", api_version="2026-03-11"
    )

    [doc] = list(connector.iter_documents("tenant-notion"))

    assert "SECRET_HASH" not in doc.title
    assert "SECRET_HASH" not in doc.body
    assert "SECRET_HASH" not in doc.canonical_ref
    assert "SECRET_HASH" not in str(doc.metadata)


@pytest.mark.parametrize(
    ("token", "database_id", "api_version"),
    [("", "db-1", "2026-03-11"), ("token", "", "2026-03-11"), ("token", "db-1", "")],
)
def test_notion_connector_requires_configuration(token, database_id, api_version):
    with pytest.raises(ValueError):
        NotionConnector(token=token, database_id=database_id, api_version=api_version)
