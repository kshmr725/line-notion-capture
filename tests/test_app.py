import app as app_module
from app import app, extract_text_event


def test_extract_text_event_text():
    raw, source_type, key = extract_text_event(
        {"source": {"userId": "U1"}, "message": {"id": "M1", "type": "text", "text": "hello"}}
    )
    assert raw == "hello"
    assert source_type == "text"
    assert key == "U1:M1"


def test_extract_text_event_url():
    raw, source_type, _ = extract_text_event(
        {"source": {"userId": "U1"}, "message": {"id": "M1", "type": "text", "text": "https://example.com"}}
    )
    assert raw == "https://example.com"
    assert source_type == "url"


def test_extract_text_event_embedded_url():
    raw, source_type, _ = extract_text_event(
        {"source": {"userId": "U1"}, "message": {"id": "M1", "type": "text", "text": "看這篇 https://example.com/a"}}
    )
    assert raw == "看這篇 https://example.com/a"
    assert source_type == "url"


def test_landing_page_is_user_facing():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Kevin Capture" in response.data
    assert b"line.me/R/ti/p/@658husbm" in response.data
    assert b"/line/webhook" not in response.data


def test_admin_dashboard_shows_webhook_url():
    client = app.test_client()
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"/line/webhook" in response.data


def test_admin_dashboard_shows_line_oa_reply_checklist():
    client = app.test_client()
    response = client.get("/admin")
    assert response.status_code == 200
    assert "LINE OA 回覆檢查".encode() in response.data
    assert "自動回應訊息".encode() in response.data
    assert "AI 聊天機器人".encode() in response.data
    assert "很抱歉，本帳號無法個別回覆".encode() in response.data


def test_debug_simulate_requires_dry_run(monkeypatch):
    app.config["DRY_RUN_VISIBLE"] = False
    response = app.test_client().post("/debug/simulate", json={"text": "hello"})
    assert response.status_code == 403


def test_debug_simulate_processes_message_in_dry_run(monkeypatch):
    app.config["DRY_RUN_VISIBLE"] = True
    monkeypatch.setattr(app_module, "create_capture_page", lambda **kwargs: "https://notion.example/page")

    class Result:
        title = "測試標題"
        category = "Inbox"
        folder = "00_Inbox_收件匣"
        category_key = "inbox"
        category_reason = "default"
        provider = "degraded"
        summary = "摘要"
        what = "這是什麼"
        key_point = "重點"
        action = "下一步"
        detail = "- 重點"
        tags = []
        template_key = "keep"
        template_label = "Keep 快速收藏"

    monkeypatch.setattr(app_module, "organize", lambda raw_text, source_type, **kwargs: Result())
    response = app.test_client().post("/debug/simulate", json={"text": "hello", "user_id": "U1"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["result"]["title"] == "測試標題"
    assert data["result"]["notion_url"] == "https://notion.example/page"


def test_process_message_event_dedupes_completed(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.capture_store.settings, "database_path", str(tmp_path / "captures.sqlite3"))
    monkeypatch.setattr(app_module, "create_capture_page", lambda **kwargs: "https://notion.example/page")
    calls = {"organize": 0}

    class Result:
        title = "測試標題"
        category = "收件匣"
        folder = "00_Inbox_收件匣"
        category_key = "inbox"
        category_reason = "default"
        provider = "gemini"
        summary = "摘要"
        what = "這是什麼"
        key_point = "重點"
        action = "下一步"
        detail = "- 重點"
        tags = []
        template_key = "keep"
        template_label = "Keep 快速收藏"

    def fake_organize(raw_text, source_type, **kwargs):
        calls["organize"] += 1
        return Result()

    monkeypatch.setattr(app_module, "organize", fake_organize)
    event = {"source": {"userId": "U1"}, "message": {"id": "M1", "type": "text", "text": "hello"}}

    first = app_module.process_message_event(event)
    second = app_module.process_message_event(event)

    assert first["status"] == "completed"
    assert second["status"] == "duplicate_completed"
    assert calls["organize"] == 1


def test_line_webhook_pushes_completion_after_initial_reply(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.capture_store.settings, "database_path", str(tmp_path / "captures.sqlite3"))
    monkeypatch.setattr(app_module, "verify_signature", lambda body, signature: True)
    monkeypatch.setattr(app_module, "create_capture_page", lambda **kwargs: "https://notion.example/page")
    replies = []
    pushes = []
    monkeypatch.setattr(app_module, "reply_text", lambda token, text: replies.append((token, text)))
    monkeypatch.setattr(app_module, "push_text", lambda user_id, text: pushes.append((user_id, text)))

    class Result:
        title = "測試標題"
        category = "AI自動化"
        folder = "50_Tech_AI自動化"
        category_key = "tech"
        category_reason = "api"
        provider = "deepseek"
        summary = "摘要"
        what = "這是什麼"
        key_point = "重點"
        action = "下一步"
        detail = "- 重點"
        tags = []
        template_key = "article"
        template_label = "文章摘要"

    monkeypatch.setattr(app_module, "organize", lambda raw_text, source_type, **kwargs: Result())

    response = app.test_client().post(
        "/line/webhook",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "source": {"type": "user", "userId": "U1"},
                    "message": {"id": "M1", "type": "text", "text": "請整理 API 自動化"},
                }
            ]
        },
        headers={"X-Line-Signature": "ok"},
    )

    assert response.status_code == 200
    assert len(replies) == 1
    assert "正在整理" in replies[0][1]
    assert pushes[0][0] == "U1"
    assert "已整理完成" in pushes[0][1]
    assert "AI自動化" in pushes[0][1]
    assert "AI：" not in pushes[0][1]
    assert "deepseek" not in pushes[0][1]


def test_line_webhook_handles_format_command(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.capture_store.settings, "database_path", str(tmp_path / "captures.sqlite3"))
    monkeypatch.setattr(app_module, "verify_signature", lambda body, signature: True)
    replies = []
    pushes = []
    monkeypatch.setattr(app_module, "reply_text", lambda token, text: replies.append((token, text)))
    monkeypatch.setattr(app_module, "push_text", lambda user_id, text: pushes.append((user_id, text)))

    response = app.test_client().post(
        "/line/webhook",
        json={
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "source": {"type": "user", "userId": "U1"},
                    "message": {"id": "M1", "type": "text", "text": "格式 文章"},
                }
            ]
        },
        headers={"X-Line-Signature": "ok"},
    )

    assert response.status_code == 200
    assert len(replies) == 1
    assert "文章摘要" in replies[0][1]
    assert pushes == []


def test_api_status_and_captures(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.capture_store.settings, "database_path", str(tmp_path / "captures.sqlite3"))
    app_module.capture_store.record_inbound(
        message_key="U1:M1",
        source_user="U1",
        source_type="text",
        raw_input="hello",
        payload={},
    )
    client = app.test_client()

    status_response = client.get("/api/status")
    captures_response = client.get("/api/captures")

    assert status_response.status_code == 200
    assert status_response.get_json()["stats"]["received"] == 1
    assert captures_response.get_json()["captures"][0]["message_key"] == "U1:M1"


def test_line_webhook_duplicate_message_does_not_show_auto_template(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.capture_store.settings, "database_path", str(tmp_path / "captures.sqlite3"))
    monkeypatch.setattr(app_module, "verify_signature", lambda body, signature: True)
    monkeypatch.setattr(app_module, "create_capture_page", lambda **kwargs: "https://notion.example/page")
    replies = []
    pushes = []
    monkeypatch.setattr(app_module, "reply_text", lambda token, text: replies.append((token, text)))
    monkeypatch.setattr(app_module, "push_text", lambda user_id, text: pushes.append((user_id, text)))

    class Result:
        title = "買生日禮物"
        category = "任務待辦"
        folder = "20_Tasks_任務待辦"
        category_key = "task"
        category_reason = "task intent"
        provider = "gemini"
        summary = "摘要"
        what = "這是什麼"
        key_point = "重點"
        action = "下一步"
        detail = "- 重點"
        tags = []
        template_key = "task"
        template_label = "任務待辦"

    monkeypatch.setattr(app_module, "organize", lambda raw_text, source_type, **kwargs: Result())
    event = {
        "type": "message",
        "replyToken": "reply-token",
        "source": {"type": "user", "userId": "U1"},
        "message": {"id": "M1", "type": "text", "text": "買生日禮物、訂餐廳、確認預算"},
    }
    payload = {"events": [event]}

    app.test_client().post("/line/webhook", json=payload, headers={"X-Line-Signature": "ok"})
    app.test_client().post("/line/webhook", json=payload, headers={"X-Line-Signature": "ok"})

    assert len(pushes) == 2
    assert "這則已整理過" in pushes[1][1]
    assert "格式：沿用原筆記" in pushes[1][1]
    assert "自動判斷" not in pushes[1][1]
