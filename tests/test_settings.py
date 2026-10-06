import settings


def test_ausente_y_corrupto_dan_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "get_data_dir", lambda: tmp_path)
    assert settings.load_settings() == {}
    (tmp_path / "settings.json").write_text("{roto", encoding="utf-8")
    assert settings.load_settings() == {}
    (tmp_path / "settings.json").write_text("[1]", encoding="utf-8")
    assert settings.load_settings() == {}


def test_save_conserva_otras_claves(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "get_data_dir", lambda: tmp_path)
    settings.save_setting("language", "pt")
    settings.save_setting("otra", 1)
    assert settings.load_settings() == {"language": "pt", "otra": 1}
