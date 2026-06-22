"""Tests de letras: parsing LRC, ajuste de timing, placeholder de reintento."""

import pytest

from audio_player import LYRICS_NOT_FOUND_TEXT

LRC_EJEMPLO = """[00:01.00]<center>Primera línea</center>
[00:03.50]<center>Segunda línea</center>
[01:00.25]<center>Tercera línea</center>
"""


class TestParsingLRC:
    def test_parsea_bloques_con_timestamps(self, player, tmp_path):
        (tmp_path / "lyrics.lrc").write_text(LRC_EJEMPLO, encoding="utf-8")
        lyrics = player.lazy_lyrics.load_lyrics_lazy(tmp_path)
        assert len(lyrics) == 3
        assert lyrics[0][0] == 1.0
        assert lyrics[1][0] == 3.5
        assert lyrics[2][0] == 60.25
        assert "Primera" in lyrics[0][1]

    def test_carpeta_sin_lrc_devuelve_vacio(self, player, tmp_path):
        assert player.lazy_lyrics.load_lyrics_lazy(tmp_path) == []

    def test_cache_se_invalida_con_remove(self, player, tmp_path):
        lrc = tmp_path / "lyrics.lrc"
        lrc.write_text(LRC_EJEMPLO, encoding="utf-8")
        player.lazy_lyrics.load_lyrics_lazy(tmp_path)

        lrc.write_text("[00:09.00]<center>Nueva</center>\n", encoding="utf-8")
        # Sin invalidar: devuelve el parse viejo
        assert len(player.lazy_lyrics.load_lyrics_lazy(tmp_path)) == 3
        player.lazy_lyrics.cache.remove(f"lyrics_{tmp_path}")
        assert len(player.lazy_lyrics.load_lyrics_lazy(tmp_path)) == 1


class TestAjusteTiming:
    def test_adjust_time_suma_offset(self, player):
        assert player._adjust_time("00:10.00", 0.5) == "00:10.50"
        assert player._adjust_time("01:59.80", 0.5) == "02:00.30"

    def test_adjust_time_no_baja_de_cero(self, player):
        assert player._adjust_time("00:00.20", -0.5) == "00:00.00"

    def test_process_lines_conserva_lineas_sin_timestamp(self, player):
        lines = ["sin timestamp\n", "[00:05.00]con timestamp\n"]
        result = player._process_lines(lines, 1.0)
        assert result[0] == "sin timestamp\n"
        assert result[1].startswith("[00:06.00]")


class TestFallbackHibrido:
    """LRCLIB estricto primero; syncedlyrics (fuzzy) solo si LRCLIB no encuentra."""

    def test_lrclib_encuentra_no_usa_fallback(self, player, tmp_path, monkeypatch):
        monkeypatch.setattr(player, "_search_lrclib", lambda a, s: "[00:01.00]hola")
        monkeypatch.setattr(
            player, "_search_syncedlyrics",
            lambda a, s: pytest.fail("No debe llamarse al fallback"),
        )
        player._fetch_lyrics_from_api("A", "B", tmp_path)
        content = (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
        assert "<center>hola</center>" in content

    def test_fallback_se_usa_cuando_lrclib_falla(self, player, tmp_path, monkeypatch):
        monkeypatch.setattr(player, "_search_lrclib", lambda a, s: "")
        monkeypatch.setattr(
            player, "_search_syncedlyrics", lambda a, s: "[00:02.00]mundo"
        )
        player._fetch_lyrics_from_api("A", "B", tmp_path)
        content = (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
        assert "<center>mundo</center>" in content
        assert LYRICS_NOT_FOUND_TEXT not in content

    def test_placeholder_si_ambos_fallan(self, player, tmp_path, monkeypatch):
        monkeypatch.setattr(player, "_search_lrclib", lambda a, s: "")
        monkeypatch.setattr(player, "_search_syncedlyrics", lambda a, s: "")
        player._fetch_lyrics_from_api("A", "B", tmp_path)
        content = (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
        assert LYRICS_NOT_FOUND_TEXT in content

    def test_search_syncedlyrics_tolera_paquete_ausente(self, player, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "syncedlyrics":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert player._search_syncedlyrics("A", "B") == ""


class TestPlaceholderReintento:
    def test_escribe_placeholder_cuando_no_hay_letras(self, player, tmp_path):
        player._write_lyrics_file(tmp_path, "A", "B", None)
        content = (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
        # El texto escrito debe coincidir con el que dispara el reintento
        assert LYRICS_NOT_FOUND_TEXT in content

    def test_letras_validas_no_contienen_placeholder(self, player, tmp_path):
        player._write_lyrics_file(
            tmp_path, "A", "B", "[00:01.00]hola\n[00:02.00]mundo"
        )
        content = (tmp_path / "lyrics.lrc").read_text(encoding="utf-8")
        assert LYRICS_NOT_FOUND_TEXT not in content
        assert "<center>hola</center>" in content


class TestAutoUnmuteVoz:
    def test_linea_en_blanco_se_detecta(self, player):
        player.lyrics = [
            (1.0, "<center>Canta</center>"),
            (2.0, "<center></center>"),
        ]
        assert player._current_lyric_is_blank(2.5) is True
        assert player._current_lyric_is_blank(1.5) is False

    def test_antes_de_primera_linea_no_es_blanco(self, player):
        player.lyrics = [(5.0, "<center>Hola</center>")]
        assert player._current_lyric_is_blank(1.0) is False

    def test_ramp_none_si_checkbox_off(self, player):
        player.auto_unmute_enabled = False
        player.mute_states["vocals"] = True
        player._auto_unmute_gain = 0.0
        assert player._auto_unmute_ramp(0, 1024, 44100) is None

    def test_ramp_sube_en_blanco_y_no_excede_uno(self, player):
        player.auto_unmute_enabled = True
        player.mute_states["vocals"] = True
        player.lyrics = [(0.0, "<center></center>")]
        player._auto_unmute_gain = 0.0
        ramp = player._auto_unmute_ramp(0, 1024, 44100)
        assert ramp is not None
        assert ramp[0] == 0.0
        assert 0.0 < ramp[-1] <= 1.0
        assert player._auto_unmute_gain == ramp[-1]

    def test_fade_dura_medio_segundo(self, player):
        player.auto_unmute_enabled = True
        player.mute_states["vocals"] = True
        player.lyrics = [(0.0, "<center></center>")]
        player._auto_unmute_gain = 0.0
        sr = 44100
        # ~0.5 s a chunks de 1024 frames hasta alcanzar ganancia plena
        chunks = 0
        pos = 0
        while player._auto_unmute_gain < 1.0 and chunks < 100:
            player._auto_unmute_ramp(pos, 1024, sr)
            pos += 1024
            chunks += 1
        # 0.5 s / (1024/44100 s por chunk) ≈ 21.5 chunks
        assert 20 <= chunks <= 23

    def test_fade_out_al_desactivar_con_ganancia_residual(self, player):
        player.auto_unmute_enabled = False
        player.mute_states["vocals"] = True
        player._auto_unmute_gain = 1.0
        ramp = player._auto_unmute_ramp(0, 1024, 44100)
        assert ramp is not None
        assert ramp[-1] < 1.0  # desciende hacia 0
