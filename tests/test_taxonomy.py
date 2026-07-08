from taxonomy import category_cover_url, category_icon, category_visual_group, classify


def test_task_intent_beats_food_keyword():
    result = classify("買生日禮物、訂餐廳、確認預算")

    assert result.key == "task"
    assert result.label == "任務待辦"
    assert result.icon == "✅"
    assert result.visual_group == "待處理"


def test_google_maps_still_routes_to_food():
    result = classify("https://maps.google.com/?q=coffee 評價 4.8 營業時間")

    assert result.key == "food"
    assert result.icon == "☕"


def test_category_visual_helpers_have_defaults():
    assert category_icon("missing") == "📥"
    assert category_visual_group("reading") == "閱讀收藏"
    assert category_cover_url("food").startswith("https://")
