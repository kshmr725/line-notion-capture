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


def test_dashboard_shows_webhook_url():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"/line/webhook" in response.data


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
        provider = "degraded"

    monkeypatch.setattr(app_module, "organize", lambda raw_text, source_type: Result())
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
        category = "Inbox"
        provider = "gemini"
        summary = "摘要"
        tags = []

    def fake_organize(raw_text, source_type):
        calls["organize"] += 1
        return Result()

    monkeypatch.setattr(app_module, "organize", fake_organize)
    event = {"source": {"userId": "U1"}, "message": {"id": "M1", "type": "text", "text": "hello"}}

    first = app_module.process_message_event(event)
    second = app_module.process_message_event(event)

    assert first["status"] == "completed"
    assert second["status"] == "duplicate_completed"
    assert calls["organize"] == 1


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
