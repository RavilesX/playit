"""Tests de letras: parsing LRC, ajuste de timing, placeholder de reintento."""

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
