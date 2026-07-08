import capture_store
import user_store


def test_user_preference_defaults_to_auto(monkeypatch, tmp_path):
    monkeypatch.setattr(capture_store.settings, "database_path", str(tmp_path / "db.sqlite3"))

    preference = user_store.get_or_create("U1")

    assert preference.default_template == "auto"
    assert preference.custom_template == ""


def test_user_preference_can_store_custom_template(monkeypatch, tmp_path):
    monkeypatch.setattr(capture_store.settings, "database_path", str(tmp_path / "db.sqlite3"))

    preference = user_store.set_template("U1", "custom", "請分成背景、重點、下一步")

    assert preference.default_template == "custom"
    assert preference.custom_template == "請分成背景、重點、下一步"
