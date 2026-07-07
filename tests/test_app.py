from app import extract_text_event


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
