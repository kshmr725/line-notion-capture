import llm_router
from llm_router import fallback_result, parse_llm_json


def test_parse_llm_json():
    result = parse_llm_json(
        '{"title":"買咖啡豆","summary":"提醒購買咖啡豆","what":"購物提醒","key_point":"咖啡豆快用完","action":"下次補貨","detail_points":["買咖啡豆"],"tags":["todo","life"]}',
        "gemini",
    )
    assert result.title == "買咖啡豆"
    assert result.category == "任務待辦"
    assert result.folder == "20_Tasks_任務待辦"
    assert result.category_icon == "✅"
    assert result.action == "下次補貨"
    assert result.tags == ["todo", "life"]
    assert result.provider == "gemini"


def test_fallback_result():
    result = fallback_result("hello world")
    assert result.provider == "degraded"
    assert result.degraded
    assert result.category == "收件匣"


def test_organize_dry_run_does_not_call_providers(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "dry_run", True)

    def fail_provider(*args, **kwargs):
        raise AssertionError("provider should not be called in dry run")

    monkeypatch.setattr(llm_router, "call_gemini", fail_provider)
    monkeypatch.setattr(llm_router, "call_deepseek", fail_provider)

    result = llm_router.organize("hello", "text")

    assert result.provider == "degraded"
    assert result.tags == ["dry-run"]


def test_organize_dry_run_uses_deterministic_category(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "dry_run", True)

    result = llm_router.organize("WHO healthy diet nutrition", "url")

    assert result.category == "健身與健康"
    assert result.folder == "73_Fitness_健身與健康"
