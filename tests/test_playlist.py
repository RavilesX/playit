"""Tests de manejo de playlist: agregar, deduplicar, remover, buscar."""
from pathlib import Path


def make_song(artist, song, path="/tmp/x"):
    return {"artist": artist, "song": song, "path": Path(path)}


class TestOnSongsLoaded:
    def test_agrega_lote(self, player):
        player._on_songs_loaded([make_song("A", "1"), make_song("B", "2")])
        assert len(player.playlist) == 2
        assert player.playlist_widget.count() == 2

    def test_descarta_duplicados(self, player):
        player._on_songs_loaded([make_song("A", "1")])
        player._on_songs_loaded([make_song("A", "1"), make_song("A", "2")])
        assert len(player.playlist) == 2
        assert ("A", "1") in player._playlist_keys

    def test_habilita_botones_con_primera_cancion(self, player):
        player._set_playback_buttons_enabled(False)
        player._on_songs_loaded([make_song("A", "1")])
        assert player.play_btn.isEnabled()


class TestRemoveAndClear:
    def test_clear_playlist_limpia_keys(self, player):
        player._on_songs_loaded([make_song("A", "1")])
        player.clear_playlist()
        assert not player.playlist
        assert not player._playlist_keys
        assert player.playlist_widget.count() == 0

    def test_remover_permite_reagregar(self, player):
        player._on_songs_loaded([make_song("A", "1")])
        player.playlist_widget.item(0).setSelected(True)
        player.remove_selected()
        assert not player.playlist
        player._on_songs_loaded([make_song("A", "1")])
        assert len(player.playlist) == 1


class TestScanFolder:
    def test_carga_json_de_biblioteca(self, player, tmp_path):
        song_dir = tmp_path / "Artista" / "Cancion"
        song_dir.mkdir(parents=True)
        (song_dir / "data.json").write_text(
            '{"Artista": {"Cancion": {"path": "x"}}}', encoding="utf-8"
        )
        player.scan_folder(tmp_path)
        assert len(player.playlist) == 1
        assert player.playlist[0]["artist"] == "Artista"
        # Re-escanear no duplica
        player.scan_folder(tmp_path)
        assert len(player.playlist) == 1


class TestBusqueda:
    def setup_playlist(self, player):
        player._on_songs_loaded([
            make_song("Los Tigres", "Jaula"),
            make_song("José José", "El Triste"),
            make_song("Los Bukis", "Necesito"),
        ])
        player._search_query = ""
        player._search_matches = []
        player._search_pos = -1

    def test_ciclo_de_coincidencias(self, player):
        self.setup_playlist(player)
        player._search_playlist("los")
        assert player.playlist_widget.currentRow() == 0
        player._search_playlist("los")
        assert player.playlist_widget.currentRow() == 2
        player._search_playlist("los")  # vuelve al primero
        assert player.playlist_widget.currentRow() == 0

    def test_insensible_a_acentos_y_mayusculas(self, player):
        self.setup_playlist(player)
        player._search_playlist("jose")
        assert player.playlist_widget.currentRow() == 1

    def test_cambio_de_query_reinicia(self, player):
        self.setup_playlist(player)
        player._search_playlist("los")
        player._search_playlist("triste")
        assert player.playlist_widget.currentRow() == 1

    def test_sin_coincidencias_no_mueve_seleccion(self, player):
        self.setup_playlist(player)
        player._search_playlist("los")
        before = player.playlist_widget.currentRow()
        player._search_playlist("zzzz")
        assert player.playlist_widget.currentRow() == before
