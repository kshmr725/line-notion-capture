import llm_router
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


def test_organize_dry_run_does_not_call_providers(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "dry_run", True)

    def fail_provider(*args, **kwargs):
        raise AssertionError("provider should not be called in dry run")

    monkeypatch.setattr(llm_router, "call_gemini", fail_provider)
    monkeypatch.setattr(llm_router, "call_deepseek", fail_provider)

    result = llm_router.organize("hello", "text")

    assert result.provider == "degraded"
    assert result.tags == ["dry-run"]
