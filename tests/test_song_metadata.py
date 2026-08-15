"""Tests de la metadata del archivo de origen (data.json)."""
import json

from demucs_worker import read_source_metadata
from lazy_resources import read_song_metadata


class FakeInfo:
    def __init__(self, bitrate):
        self.bitrate = bitrate


class FakeAudio:
    def __init__(self, tags, bitrate=320000):
        self.tags = tags
        self.info = FakeInfo(bitrate)


class TestReadSourceMetadata:
    def test_tags_id3(self, monkeypatch):
        tags = {
            "TPE1": ["Soda Stereo"], "TIT2": ["De Música Ligera"],
            "TALB": ["Canción Animal"], "TDRC": ["1990-08-07"],
            "TCON": ["Rock"],
        }
        monkeypatch.setattr("mutagen.File", lambda *a, **k: FakeAudio(tags))
        # Artista y canción no se guardan: ya son las claves del data.json.
        assert read_source_metadata("x.mp3") == {
            "album": "Canción Animal", "anio": "1990", "genero": "Rock",
            "formato": "MP3", "kbps": 320,
        }

    def test_tags_vorbis_y_mp4(self, monkeypatch):
        monkeypatch.setattr(
            "mutagen.File",
            lambda *a, **k: FakeAudio({"album": ["A"], "\xa9gen": ["Pop"]}, 128000),
        )
        meta = read_source_metadata("x.flac")
        assert meta == {"album": "A", "genero": "Pop",
                        "formato": "FLAC", "kbps": 128}

    def test_archivo_sin_tags_conserva_formato(self, monkeypatch):
        monkeypatch.setattr("mutagen.File", lambda *a, **k: FakeAudio(None, 0))
        assert read_source_metadata("x.wav") == {"formato": "WAV"}

    def test_formato_no_reconocido(self, monkeypatch):
        monkeypatch.setattr("mutagen.File", lambda *a, **k: None)
        assert read_source_metadata("x.bin") == {"formato": "BIN"}

    def test_sin_extension(self, monkeypatch):
        monkeypatch.setattr("mutagen.File", lambda *a, **k: None)
        assert read_source_metadata("cancion") == {}

    def test_mutagen_lanza(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("archivo corrupto")

        monkeypatch.setattr("mutagen.File", boom)
        assert read_source_metadata("x.mp3") == {"formato": "MP3"}


class TestReadSongMetadata:
    def test_lee_el_bloque_metadata(self, tmp_path):
        meta = {"album": "Disco", "kbps": 320}
        (tmp_path / "data.json").write_text(
            json.dumps({"A": {"S": {"path": str(tmp_path), "metadata": meta}}}),
            encoding="utf-8",
        )
        assert read_song_metadata(tmp_path) == meta

    def test_json_viejo_sin_metadata(self, tmp_path):
        (tmp_path / "data.json").write_text(
            json.dumps({"A": {"S": {"path": str(tmp_path)}}}), encoding="utf-8"
        )
        assert read_song_metadata(tmp_path) == {}

    def test_sin_json(self, tmp_path):
        assert read_song_metadata(tmp_path) == {}


class TestSongInfoDialog:
    """El diálogo toma artista/canción de la estructura del json, no del bloque."""

    def _dialog(self, app, metadata):
        from dialogs import SongInfoDialog
        return SongInfoDialog(None, "Soda Stereo", "Persiana Americana", metadata)

    def test_muestra_artista_y_cancion_recibidos(self, app):
        html = self._dialog(app, {"album": "Signos"})._build_html()
        assert "Soda Stereo" in html and "Persiana Americana" in html
        assert "Signos" in html

    def test_campos_faltantes_como_desconocido(self, app):
        from dialogs import SongInfoDialog
        html = self._dialog(app, {})._build_html()
        assert html.count(SongInfoDialog.UNKNOWN) == len(SongInfoDialog.FIELDS)

    def test_escapa_html_de_los_tags(self, app):
        html = self._dialog(app, {"album": "AT&T <sic>"})._build_html()
        assert "AT&amp;T &lt;sic&gt;" in html
