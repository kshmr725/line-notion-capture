from llm_router import LLMResult
import notion_writer


def test_create_capture_page_uses_database_id(monkeypatch):
    monkeypatch.setattr(notion_writer.settings, "dry_run", False)
    monkeypatch.setattr(notion_writer.settings, "notion_token", "secret")
    monkeypatch.setattr(notion_writer.settings, "notion_database_id", "db123")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"url": "https://notion.example/page"}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(notion_writer.requests, "post", fake_post)
    result = LLMResult(
        title="測試",
        summary="摘要",
        category="Inbox",
        tags=["tag"],
        provider="gemini",
    )

    url = notion_writer.create_capture_page(result, "原文", "U1", "text", "M1")

    assert url == "https://notion.example/page"
    assert captured["json"]["parent"] == {"database_id": "db123"}
    child_types = [child["type"] for child in captured["json"]["children"]]
    assert child_types == ["heading_2", "paragraph", "heading_2", "paragraph", "heading_2", "paragraph"]
    assert captured["json"]["children"][0]["heading_2"]["rich_text"][0]["text"]["content"] == "摘要"


def test_create_capture_page_dry_run_does_not_call_notion(monkeypatch):
    monkeypatch.setattr(notion_writer.settings, "dry_run", True)

    def fail_post(*args, **kwargs):
        raise AssertionError("Notion API should not be called in dry run")

    monkeypatch.setattr(notion_writer.requests, "post", fail_post)
    result = LLMResult(
        title="測試",
        summary="摘要",
        category="Inbox",
        tags=[],
        provider="degraded",
    )

    url = notion_writer.create_capture_page(result, "原文", "U1", "text", "M1")

    assert url == "https://notion.example/dry-run"
