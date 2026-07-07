from llm_router import fallback_result, parse_llm_json


def test_parse_llm_json():
    result = parse_llm_json(
        '{"title":"買咖啡豆","summary":"提醒購買咖啡豆","category":"Task","tags":["todo","life"]}',
        "gemini",
    )
    assert result.title == "買咖啡豆"
    assert result.category == "Task"
    assert result.tags == ["todo", "life"]
    assert result.provider == "gemini"


def test_fallback_result():
    result = fallback_result("hello world")
    assert result.provider == "degraded"
    assert result.degraded
    assert result.category == "Inbox"
