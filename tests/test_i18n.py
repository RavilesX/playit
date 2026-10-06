import json

import i18n


def test_sin_traduccion_devuelve_espanol(tmp_path, monkeypatch):
    i18n.load_language("es")
    assert i18n.tr("Hola") == "Hola"


def test_traduce_y_cae_a_espanol(tmp_path, monkeypatch):
    (tmp_path / "locales").mkdir()
    (tmp_path / "locales" / "en.json").write_text(
        json.dumps({"Hola": "Hello"}), encoding="utf-8")
    monkeypatch.setattr(i18n, "resource_path", lambda p: str(tmp_path / p))
    assert i18n.load_language("en") == "en"
    assert i18n.tr("Hola") == "Hello"
    assert i18n.tr("Adiós") == "Adiós"
    i18n.load_language("es")


def test_codigo_desconocido_y_json_roto(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "resource_path", lambda p: str(tmp_path / p))
    assert i18n.load_language("xx") == "es"
    assert i18n.load_language("pt") == "pt"  # archivo ausente: no lanza
    assert i18n.tr("Hola") == "Hola"
    i18n.load_language("es")


def test_N_es_identidad():
    assert i18n.N_("Hola") == "Hola"


def test_menu_idioma_guarda_preferencia(player, monkeypatch):
    import audio_player
    guardado = {}
    monkeypatch.setattr(audio_player, "save_setting", lambda k, v: guardado.update({k: v}))
    monkeypatch.setattr(audio_player, "styled_message_box", lambda *a, **k: None)
    player._set_language("pt")
    assert guardado == {"language": "pt"}
    guardado.clear()
    player._set_language(i18n.current_language())  # mismo idioma: no hace nada
    assert guardado == {}


def test_placeholders_de_las_traducciones_coinciden():
    """Un {nombre} de más o de menos revienta .format() en tiempo de ejecución."""
    import re
    from pathlib import Path
    campo = re.compile(r"\{(\w+)(?:[:!][^}]*)?\}")
    for code in ("en", "pt"):
        data = json.loads((Path(__file__).parent.parent / "locales" / f"{code}.json")
                          .read_text(encoding="utf-8"))
        for clave, valor in data.items():
            if valor:
                assert set(campo.findall(clave)) == set(campo.findall(valor)), (code, clave)
