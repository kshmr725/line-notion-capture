from llm_router import LLMResult
import notion_writer


def test_create_capture_page_uses_database_id(monkeypatch):
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
