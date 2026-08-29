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

    def test_duplicado_completa_duracion_faltante(self, player):
        """Una canción agregada mientras Demucs corría (data.json ya escrito,
        stems todavía no) entra sin duración; el re-escaneo debe completarla
        en vez de descartarse por duplicada."""
        from ui_components import PlaylistItemDelegate

        sin_duracion = make_song("A", "1")
        sin_duracion["duration"] = ""
        player._on_songs_loaded([sin_duracion])

        con_duracion = make_song("A", "1")
        con_duracion["duration"] = "3:21"
        player._on_songs_loaded([con_duracion])

        assert len(player.playlist) == 1
        assert player.playlist[0]["duration"] == "3:21"
        assert player.playlist_widget.item(0).data(
            PlaylistItemDelegate.DURATION_ROLE) == "3:21"

    def test_duplicado_no_pisa_duracion_existente(self, player):
        con_duracion = make_song("A", "1")
        con_duracion["duration"] = "3:21"
        player._on_songs_loaded([con_duracion])

        otra = make_song("A", "1")
        otra["duration"] = "9:99"
        player._on_songs_loaded([otra])

        assert player.playlist[0]["duration"] == "3:21"

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


class TestOrdenamiento:
    def setup_playlist(self, player):
        player._on_songs_loaded([
            make_song("Cielo", "Zapato"),
            make_song("Alfa", "Mango"),
            make_song("Beta", "Arbol"),
        ])

    def test_orden_por_artista(self, player):
        self.setup_playlist(player)
        player.sort_playlist("artist")
        assert [s['artist'] for s in player.playlist] == ["Alfa", "Beta", "Cielo"]
        assert player.sort_label.text() == "Artista A-Z"

    def test_orden_aleatorio_conserva_las_canciones(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr("random.shuffle", lambda seq: seq.reverse())
        player.sort_playlist("random")
        assert [s['song'] for s in player.playlist] == ["Arbol", "Mango", "Zapato"]
        assert player.playlist_widget.count() == 3
        assert player.sort_label.text() == "Aleatorio"

    def test_orden_aleatorio_preserva_la_cancion_actual(self, player, monkeypatch):
        self.setup_playlist(player)
        player.current_index = 0
        actual = player.playlist[0]
        monkeypatch.setattr("random.shuffle", lambda seq: seq.reverse())
        player.sort_playlist("random")
        assert player.playlist[player.current_index] is actual

    def test_boton_cicla_hasta_aleatorio(self, player):
        self.setup_playlist(player)
        for _ in range(len(player._SORT_MODES)):
            player._cycle_sort()
        assert player.sort_label.text() == player._SORT_MODES[-1][2]
        player._cycle_sort()
        assert player.sort_label.text() == "Artista A-Z"


class TestQueue:
    """Cola de reproducción ('Agregar a la cola' / 'Administrar cola')."""

    def setup_playlist(self, player):
        player._on_songs_loaded([
            make_song("A", "1"), make_song("B", "2"), make_song("C", "3"),
        ])

    def test_toggle_agrega_y_quita(self, player):
        self.setup_playlist(player)
        song = player.playlist[1]
        assert not player._is_queued(song)
        player._toggle_queue(song)
        assert player._is_queued(song)
        assert player.play_queue == [song]
        player._toggle_queue(song)
        assert not player._is_queued(song)
        assert player.play_queue == []

    def test_play_next_consume_cola_en_orden_fifo(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        segunda, tercera = player.playlist[1], player.playlist[2]
        player._toggle_queue(segunda)
        player._toggle_queue(tercera)
        player.current_index = 0

        player.play_next()
        assert player.current_index == 1
        assert player.play_queue == [tercera]

        player.play_next()
        assert player.current_index == 2
        assert player.play_queue == []

        # Cola vacía: sigue el orden normal de la playlist.
        player.play_next()
        assert player.current_index == 0

    def test_play_next_salta_cancion_encolada_y_luego_eliminada(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        borrada = player.playlist[1]
        player._toggle_queue(borrada)
        player.playlist_widget.item(1).setSelected(True)
        player.current_index = 0
        player.remove_selected()
        assert player.play_queue == []  # _purge_queue la descartó

        player.play_next()
        assert player.current_index == 1  # avance normal, sin la eliminada

    def test_remove_selected_purga_la_cola(self, player):
        self.setup_playlist(player)
        song = player.playlist[1]
        player._toggle_queue(song)
        player.playlist_widget.item(1).setSelected(True)
        player.remove_selected()
        assert player.play_queue == []

    def test_clear_playlist_vacia_la_cola(self, player):
        self.setup_playlist(player)
        player._toggle_queue(player.playlist[0])
        player.clear_playlist()
        assert player.play_queue == []

    def test_sort_preserva_la_cola_por_identidad(self, player):
        self.setup_playlist(player)
        song = player.playlist[1]
        player._toggle_queue(song)
        player.sort_playlist("song", reverse=True)
        assert player.play_queue == [song]

    def test_targets_multiseleccion_si_el_click_cae_dentro(self, player):
        self.setup_playlist(player)
        for row in (0, 1, 2):
            player.playlist_widget.item(row).setSelected(True)
        clicked = player.playlist_widget.item(1)
        targets = player._queue_action_targets(clicked)
        assert {id(s) for s in targets} == {id(s) for s in player.playlist}

    def test_targets_un_solo_item_si_el_click_cae_fuera_de_la_seleccion(self, player):
        self.setup_playlist(player)
        player.playlist_widget.item(0).setSelected(True)
        clicked = player.playlist_widget.item(2)  # no seleccionado
        targets = player._queue_action_targets(clicked)
        assert targets == [player.playlist[2]]

    def test_targets_un_solo_item_sin_seleccion_multiple(self, player):
        self.setup_playlist(player)
        player.playlist_widget.item(1).setSelected(True)
        clicked = player.playlist_widget.item(1)
        targets = player._queue_action_targets(clicked)
        assert targets == [player.playlist[1]]

    def test_toggle_many_agrega_todos_los_seleccionados(self, player):
        self.setup_playlist(player)
        songs = list(player.playlist)
        player._toggle_queue_many(songs, add=True)
        assert {id(s) for s in player.play_queue} == {id(s) for s in songs}

    def test_toggle_many_no_duplica_los_ya_encolados(self, player):
        self.setup_playlist(player)
        player._toggle_queue(player.playlist[0])
        player._toggle_queue_many(player.playlist, add=True)
        assert len(player.play_queue) == 3

    def test_toggle_many_quita_todos_los_seleccionados(self, player):
        self.setup_playlist(player)
        player._toggle_queue_many(player.playlist, add=True)
        player._toggle_queue_many(player.playlist[:2], add=False)
        assert player.play_queue == [player.playlist[2]]

    def test_menu_agregar_vs_eliminar_con_multiseleccion_mixta(self, player):
        """Selección con algunos encolados y otros no: el menú debe ofrecer
        'Agregar' (afecta solo a los que faltan), no 'Eliminar'."""
        self.setup_playlist(player)
        player._toggle_queue(player.playlist[0])
        for row in (0, 1, 2):
            player.playlist_widget.item(row).setSelected(True)
        clicked = player.playlist_widget.item(1)
        targets = player._queue_action_targets(clicked)
        add_mode = not (targets and all(player._is_queued(s) for s in targets))
        assert add_mode is True

        player._toggle_queue_many(targets, add_mode)
        assert len(player.play_queue) == 3

    def test_indicador_se_prende_y_apaga_con_toggle(self, player):
        from ui_components import PlaylistItemDelegate

        self.setup_playlist(player)
        song = player.playlist[1]
        item = player.playlist_widget.item(1)
        assert not item.data(PlaylistItemDelegate.QUEUE_ROLE)

        player._toggle_queue(song)
        assert item.data(PlaylistItemDelegate.QUEUE_ROLE) is True
        # Los demás renglones no se prenden solos.
        assert not player.playlist_widget.item(0).data(PlaylistItemDelegate.QUEUE_ROLE)

        player._toggle_queue(song)
        assert not item.data(PlaylistItemDelegate.QUEUE_ROLE)

    def test_indicador_con_toggle_many(self, player):
        from ui_components import PlaylistItemDelegate

        self.setup_playlist(player)
        player._toggle_queue_many(player.playlist, add=True)
        for row in range(3):
            assert player.playlist_widget.item(row).data(PlaylistItemDelegate.QUEUE_ROLE)

        player._toggle_queue_many(player.playlist[:2], add=False)
        assert not player.playlist_widget.item(0).data(PlaylistItemDelegate.QUEUE_ROLE)
        assert not player.playlist_widget.item(1).data(PlaylistItemDelegate.QUEUE_ROLE)
        assert player.playlist_widget.item(2).data(PlaylistItemDelegate.QUEUE_ROLE)

    def test_indicador_se_apaga_al_consumir_de_la_cola(self, player, monkeypatch):
        from ui_components import PlaylistItemDelegate

        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        song = player.playlist[1]
        player._toggle_queue(song)
        player.current_index = 0

        player.play_next()  # consume la canción encolada

        item = next(
            player.playlist_widget.item(r) for r in range(3)
            if player.playlist[r] is song
        )
        assert not item.data(PlaylistItemDelegate.QUEUE_ROLE)

    def test_indicador_se_apaga_al_quitar_desde_remove_selected(self, player):
        from ui_components import PlaylistItemDelegate

        self.setup_playlist(player)
        player._toggle_queue(player.playlist[1])
        player.playlist_widget.item(1).setSelected(True)
        player.remove_selected()
        # La canción restante que quedó en su lugar no debe heredar el punto.
        for row in range(player.playlist_widget.count()):
            assert not player.playlist_widget.item(row).data(PlaylistItemDelegate.QUEUE_ROLE)


class TestTagMutes:
    """Al consumir una canción de la cola, sus tags (Batería/Bajo/Voz/Otros)
    mutean esas pistas y encienden el resto."""

    def setup_playlist(self, player):
        player._on_songs_loaded([
            make_song("A", "1"), make_song("B", "2"), make_song("C", "3"),
        ])

    def test_tags_mutean_pistas_nombradas_y_encienden_el_resto(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        player.playlist[1]["tags"] = "Batería, Voz"
        player._toggle_queue(player.playlist[1])
        player.current_index = 0

        player.play_next()

        assert player.mute_states == {
            "drums": True, "vocals": True, "bass": False, "other": False,
        }

    def test_tags_sin_acentos_y_alias_voz_vocal(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        player.playlist[1]["tags"] = "bajo"
        player._toggle_queue(player.playlist[1])
        player.current_index = 0

        player.play_next()

        assert player.mute_states == {
            "drums": False, "vocals": False, "bass": True, "other": False,
        }

    def test_sin_tags_reconocidas_no_toca_el_mute(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        player.playlist[1]["tags"] = "instrumental"
        player._toggle_queue(player.playlist[1])
        player.current_index = 0
        player.set_mute("bass", True)

        player.play_next()

        assert player.mute_states["bass"] is True

    def test_avance_normal_sin_cola_no_toca_el_mute(self, player, monkeypatch):
        self.setup_playlist(player)
        monkeypatch.setattr(player, "play_current", lambda: None)
        player.playlist[1]["tags"] = "Batería"
        player.current_index = 0
        player.set_mute("vocals", True)

        player.play_next()  # sin cola: avanza secuencial, ignora tags

        assert player.mute_states == {
            "drums": False, "vocals": True, "bass": False, "other": False,
        }
