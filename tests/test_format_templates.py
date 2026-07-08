from format_templates import choose_template, format_help, normalize_template_key


def test_normalize_template_aliases():
    assert normalize_template_key("文章") == "article"
    assert normalize_template_key("地點") == "place"
    assert normalize_template_key("自訂") == "custom"


def test_choose_template_auto_by_category():
    assert choose_template("auto", "food", "url").key == "place"
    assert choose_template("auto", "reading", "text").key == "reading"
    assert choose_template("auto", "tech", "url").key == "article"
    assert choose_template("auto", "inbox", "text").key == "keep"


def test_format_help_lists_custom_command():
    assert "格式 自訂" in format_help("auto")
