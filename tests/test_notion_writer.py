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

    def fake_get(url, headers, timeout):
        captured["get_url"] = url

        class GetResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "properties": {
                        "Name": {},
                        "Status": {},
                        "Category": {},
                        "Source User": {},
                        "Source Type": {},
                        "Raw Input": {},
                        "Summary": {},
                        "Tags": {},
                        "AI Provider": {},
                        "LINE Message ID": {},
                        "Created At": {},
                        "Format": {},
                    }
                }

        return GetResponse()

    def fake_patch(url, headers, json, timeout):
        captured.setdefault("patches", []).append({"url": url, "json": json})
        return Response()

    monkeypatch.setattr(notion_writer.requests, "get", fake_get)
    monkeypatch.setattr(notion_writer.requests, "patch", fake_patch)
    monkeypatch.setattr(notion_writer.requests, "post", fake_post)
    result = LLMResult(
        title="測試",
        summary="摘要",
        category="收件匣",
        folder="00_Inbox_收件匣",
        category_key="inbox",
        category_reason="default",
        what="這是什麼",
        key_point="重點",
        action="下一步",
        detail="- 第一點\n- 第二點",
        tags=["tag"],
        provider="gemini",
        template_key="article",
        template_label="文章摘要",
    )

    url = notion_writer.create_capture_page(result, "原文", "U1", "text", "M1")

    assert url == "https://notion.example/page"
    assert captured["json"]["parent"] == {"database_id": "db123"}
    child_types = [child["type"] for child in captured["json"]["children"]]
    assert child_types[:7] == ["callout", "callout", "callout", "callout", "callout", "divider", "heading_2"]
    assert captured["json"]["children"][0]["callout"]["rich_text"][0]["text"]["content"].startswith("分類：")
    assert "分類入口" in captured["json"]["children"][1]["callout"]["rich_text"][0]["text"]["content"]
    assert captured["json"]["properties"]["Format"]["select"]["name"] == "文章摘要"
    assert captured["json"]["properties"]["Category Page"]["url"].startswith("https://app.notion.com/p/")
    append_calls = [patch for patch in captured["patches"] if "/v1/blocks/" in patch["url"]]
    assert append_calls
    assert append_calls[0]["json"]["children"][0]["type"] == "bulleted_list_item"


def test_create_capture_page_dry_run_does_not_call_notion(monkeypatch):
    monkeypatch.setattr(notion_writer.settings, "dry_run", True)

    def fail_post(*args, **kwargs):
        raise AssertionError("Notion API should not be called in dry run")

    monkeypatch.setattr(notion_writer.requests, "post", fail_post)
    result = LLMResult(
        title="測試",
        summary="摘要",
        category="收件匣",
        folder="00_Inbox_收件匣",
        category_key="inbox",
        category_reason="default",
        what="這是什麼",
        key_point="重點",
        action="下一步",
        detail="- 第一點",
        tags=[],
        provider="degraded",
    )

    url = notion_writer.create_capture_page(result, "原文", "U1", "text", "M1")

    assert url == "https://notion.example/dry-run"
