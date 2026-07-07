import capture_store


def test_record_inbound_creates_and_dedupes(tmp_path, monkeypatch):
    db = tmp_path / "captures.sqlite3"
    monkeypatch.setattr(capture_store.settings, "database_path", str(db))

    record, created = capture_store.record_inbound(
        message_key="U1:M1",
        source_user="U1",
        source_type="text",
        raw_input="hello",
        payload={"message": {"id": "M1"}},
    )
    assert created
    assert record.status == "received"

    duplicate, created_again = capture_store.record_inbound(
        message_key="U1:M1",
        source_user="U1",
        source_type="text",
        raw_input="hello",
        payload={"message": {"id": "M1"}},
    )
    assert not created_again
    assert duplicate.duplicate_count == 1


def test_mark_completed_and_stats(tmp_path, monkeypatch):
    db = tmp_path / "captures.sqlite3"
    monkeypatch.setattr(capture_store.settings, "database_path", str(db))
    capture_store.record_inbound(
        message_key="U1:M1",
        source_user="U1",
        source_type="text",
        raw_input="hello",
        payload={},
    )
    capture_store.mark_processing("U1:M1")
    capture_store.mark_completed(
        message_key="U1:M1",
        title="標題",
        category="Inbox",
        provider="gemini",
        notion_url="https://notion.example/page",
    )

    record = capture_store.get_capture("U1:M1")
    assert record.status == "completed"
    assert record.title == "標題"
    assert capture_store.stats()["completed"] == 1
