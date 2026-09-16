"""Tests del lote del diálogo de división (dialogs.SplitDialog + process_batch).

Lo que se fija aquí: el nombre "Artista - Canción" se resuelve solo, los
archivos que no cumplen se preguntan ANTES de encolar nada (si no, cada
diálogo pararía la cola en plena separación) y el lote entra completo a
`demucs_queue`.
"""
import time

import pytest
from PyQt6.QtWidgets import QMessageBox

import audio_player
import dialogs
from dialogs import (
    BatchNameDialog,
    BatchTimingDialog,
    SplitDialog,
    format_elapsed,
    guess_artist_song,
    parse_artist_song,
)


class TestParseNombres:
    def test_patron_con_guion(self):
        assert parse_artist_song("/m/soda stereo - de musica ligera.mp3") == (
            "Soda Stereo", "De Musica Ligera"
        )

    def test_toma_el_ultimo_guion_como_separador(self):
        assert parse_artist_song("/m/AC-DC - Back In Black.flac") == ("Ac", "Back In Black")

    def test_sin_guion_es_none(self):
        assert parse_artist_song("/m/01 track.mp3") is None

    def test_lado_vacio_es_none(self):
        assert parse_artist_song("/m/Artista - .mp3") is None

    def test_guess_siempre_devuelve_algo(self):
        assert guess_artist_song("/m/01 track.mp3") == ("", "01 Track")
        assert guess_artist_song("/m/Artista - .mp3") == ("Artista", "")


class TestResolveBatchNames:
    """_resolve_batch_names pregunta solo por los archivos sin guion."""

    def _dialog(self, app):
        return SplitDialog(None)

    def test_ninguno_pregunta_si_todos_cumplen(self, app, monkeypatch):
        dialog = self._dialog(app)
        monkeypatch.setattr(
            BatchNameDialog, "exec", lambda self: pytest.fail("no debió preguntar")
        )
        jobs = dialog._resolve_batch_names(["/m/A - Uno.mp3", "/m/B - Dos.mp3"])
        assert jobs == [
            {"artist": "A", "song": "Uno", "file_path": "/m/A - Uno.mp3"},
            {"artist": "B", "song": "Dos", "file_path": "/m/B - Dos.mp3"},
        ]
        dialog.deleteLater()

    def test_pregunta_por_cada_archivo_sin_guion(self, app, monkeypatch):
        dialog = self._dialog(app)
        asked = []

        def fake_exec(self):
            asked.append(self.song.text())
            self.artist.setText("Manual")
            self.song.setText(f"Tema {len(asked)}")
            return BatchNameDialog.DialogCode.Accepted

        monkeypatch.setattr(BatchNameDialog, "exec", fake_exec)
        jobs = dialog._resolve_batch_names(["/m/uno.mp3", "/m/A - Dos.mp3", "/m/tres.mp3"])

        assert asked == ["Uno", "Tres"]          # solo los que no cumplen
        assert [j["song"] for j in jobs] == ["Tema 1", "Dos", "Tema 2"]
        assert [j["artist"] for j in jobs] == ["Manual", "A", "Manual"]
        dialog.deleteLater()

    def test_omitir_deja_fuera_solo_ese_archivo(self, app, monkeypatch):
        dialog = self._dialog(app)
        monkeypatch.setattr(BatchNameDialog, "exec", lambda self: BatchNameDialog.SKIP)
        jobs = dialog._resolve_batch_names(["/m/uno.mp3", "/m/A - Dos.mp3"])
        assert [j["file_path"] for j in jobs] == ["/m/A - Dos.mp3"]
        dialog.deleteLater()

    def test_cancelar_descarta_el_lote_completo(self, app, monkeypatch):
        dialog = self._dialog(app)
        monkeypatch.setattr(
            BatchNameDialog, "exec", lambda self: BatchNameDialog.DialogCode.Rejected
        )
        assert dialog._resolve_batch_names(["/m/A - Uno.mp3", "/m/dos.mp3"]) == []
        dialog.deleteLater()


class TestConfirmDuplicates:
    """Dos trabajos con el mismo artista/canción escriben la misma carpeta."""

    def test_sin_repetidos_no_pregunta(self, app, monkeypatch):
        dialog = SplitDialog(None)
        monkeypatch.setattr(
            dialogs, "styled_message_box", lambda *a, **k: pytest.fail("no debió avisar")
        )
        assert dialog._confirm_duplicates([
            {"artist": "A", "song": "Uno"}, {"artist": "A", "song": "Dos"},
        ]) is True
        dialog.deleteLater()

    def test_repetido_sin_importar_mayusculas(self, app, monkeypatch):
        dialog = SplitDialog(None)
        shown = []

        def fake_box(parent, title, text, *a, **k):
            shown.append(text)
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(dialogs, "styled_message_box", fake_box)
        assert dialog._confirm_duplicates([
            {"artist": "A", "song": "Uno"}, {"artist": "a", "song": "UNO"},
        ]) is False
        assert "A - Uno" in shown[0] or "a - UNO" in shown[0]
        dialog.deleteLater()


class TestProcessBatch:
    """process_batch encola todo de una vez y arranca el primer trabajo."""

    def test_encola_todo_y_arranca_uno(self, player, monkeypatch):
        player.demucs_queue.clear()
        player.demucs_active = False
        started = []
        monkeypatch.setattr(player, "_start_demucs_job", lambda job: started.append(job))

        player.process_batch([
            {"artist": "A", "song": "Uno", "file_path": "/m/1.mp3"},
            {"artist": "B", "song": "Dos", "file_path": "/m/2.mp3"},
            {"artist": "C", "song": "Tres", "file_path": "/m/3.mp3"},
        ])

        assert len(started) == 1 and started[0]["song"] == "Uno"
        assert [j["song"] for j in player.demucs_queue] == ["Dos", "Tres"]
        # silencia los diálogos de error por track en medio del lote
        assert player.processing_multiple is True
        assert player.last_in_queue == {"artist": "C", "song": "Tres"}
        player.demucs_queue.clear()

    def test_con_worker_activo_solo_encola(self, player, monkeypatch):
        player.demucs_queue.clear()
        player.demucs_active = True
        monkeypatch.setattr(
            player, "_start_demucs_job", lambda job: pytest.fail("no debió arrancar")
        )
        player.process_batch([{"artist": "A", "song": "Uno", "file_path": "/m/1.mp3"}])
        assert len(player.demucs_queue) == 1
        player.demucs_queue.clear()
        player.demucs_active = False

    def test_lote_vacio_no_hace_nada(self, player, monkeypatch):
        player.demucs_queue.clear()
        player.demucs_active = False
        monkeypatch.setattr(
            player, "_start_demucs_job", lambda job: pytest.fail("no debió arrancar")
        )
        player.process_batch([])
        assert player.demucs_queue == []

    def test_cronometro_se_propaga_a_cada_trabajo(self, player, monkeypatch):
        player.demucs_queue.clear()
        player.demucs_active = True
        monkeypatch.setattr(player, "_start_demucs_job", lambda job: None)
        player.process_batch(
            [{"artist": "A", "song": "Uno", "file_path": "/m/1.mp3"},
             {"artist": "B", "song": "Dos", "file_path": "/m/2.mp3"}],
            timed=True,
        )
        assert all(j["timed"] for j in player.demucs_queue)
        player.demucs_queue.clear()
        player.demucs_active = False


class TestFormatElapsed:
    def test_minutos_y_segundos(self):
        assert format_elapsed(192) == "3 min 12 s"

    def test_horas_solo_cuando_las_hay(self):
        assert format_elapsed(59) == "0 min 59 s"
        assert format_elapsed(3 * 3600 + 5 * 60 + 2) == "3 h 5 min 2 s"

    def test_redondea(self):
        assert format_elapsed(59.6) == "1 min 0 s"


class TestCronometroLote:
    """_finish_timed_job: modal suelto por canción vs. un resumen por lote."""

    def _job(self, song, batch_id=7, ago=60.0):
        return {"artist": "A", "song": song, "timed": True,
                "batch_id": batch_id, "t0": time.monotonic() - ago}

    def _quiet(self, player, monkeypatch):
        """Captura los dos diálogos que puede sacar el cronómetro."""
        modals, summaries = [], []
        monkeypatch.setattr(audio_player, "styled_message_box",
                            lambda *a, **k: modals.append(a))
        monkeypatch.setattr(player, "_show_batch_timing_summary", summaries.append)
        player.demucs_queue.clear()
        player._batch_timings.clear()
        player._current_demucs_job = None
        return modals, summaries

    def test_en_medio_del_lote_solo_anota(self, player, monkeypatch):
        modals, summaries = self._quiet(player, monkeypatch)
        running, queued = self._job("Dos"), self._job("Tres")
        player.demucs_queue.append(queued)
        player._current_demucs_job = running

        player._finish_timed_job(self._job("Uno"), "CUDA")

        assert summaries == [] and modals == []
        assert [r["song"] for r in player._batch_timings[7]] == ["Uno"]

    def test_el_ultimo_dispara_el_resumen(self, player, monkeypatch):
        modals, summaries = self._quiet(player, monkeypatch)
        last = self._job("Dos")
        player.demucs_queue.append(last)
        player._current_demucs_job = last
        player._finish_timed_job(self._job("Uno"), "CUDA")
        assert summaries == []

        # el último: ya no queda nada de ese lote ni en cola ni corriendo
        player.demucs_queue.clear()
        player._current_demucs_job = None
        player._finish_timed_job(last, "CUDA")

        assert summaries == [7]
        assert [r["song"] for r in player._batch_timings[7]] == ["Uno", "Dos"]
        assert modals == []

    def test_un_trabajo_suelto_en_medio_no_alarga_el_lote(self, player, monkeypatch):
        _, summaries = self._quiet(player, monkeypatch)
        # canción agregada a mano mientras corre el lote: sin batch_id
        player.demucs_queue.append({"artist": "X", "song": "Suelta",
                                    "timed": False, "t0": time.monotonic()})
        player._finish_timed_job(self._job("Uno"), "CUDA")
        assert summaries == [7]

    def test_dos_lotes_no_mezclan_renglones(self, player, monkeypatch):
        _, summaries = self._quiet(player, monkeypatch)
        otro = self._job("Otro", batch_id=8)
        player.demucs_queue.append(otro)
        player._current_demucs_job = otro

        player._finish_timed_job(self._job("Uno", batch_id=7), "CUDA")

        assert summaries == [7]                      # el 7 ya no tiene pendientes
        assert 8 not in player._batch_timings        # el 8 sigue corriendo
        assert [r["song"] for r in player._batch_timings[7]] == ["Uno"]

    def test_error_anota_renglon_y_cierra_el_lote(self, player, monkeypatch):
        _, summaries = self._quiet(player, monkeypatch)
        player._finish_timed_job(self._job("Uno"), "", failed=True)
        assert summaries == [7]
        assert player._batch_timings[7][0]["failed"] is True

    def test_cancion_suelta_saca_su_modal(self, player, monkeypatch):
        modals, summaries = self._quiet(player, monkeypatch)
        job = self._job("Uno")
        del job["batch_id"]
        player._finish_timed_job(job, "CUDA")
        assert len(modals) == 1 and summaries == []

    def test_cancion_suelta_que_falla_no_saca_modal(self, player, monkeypatch):
        modals, _ = self._quiet(player, monkeypatch)
        job = self._job("Uno")
        del job["batch_id"]
        player._finish_timed_job(job, "", failed=True)
        assert modals == []

    def test_sin_cronometro_no_hace_nada(self, player, monkeypatch):
        modals, summaries = self._quiet(player, monkeypatch)
        job = self._job("Uno")
        job["timed"] = False
        player._finish_timed_job(job, "CUDA")
        player._finish_timed_job(None, "CUDA")
        assert modals == [] and summaries == [] and player._batch_timings == {}

    def test_process_batch_marca_un_id_por_lote(self, player, monkeypatch):
        player.demucs_queue.clear()
        player.demucs_active = True
        monkeypatch.setattr(player, "_start_demucs_job", lambda job: None)

        player.process_batch([{"artist": "A", "song": "Uno", "file_path": "/m/1.mp3"},
                              {"artist": "B", "song": "Dos", "file_path": "/m/2.mp3"}],
                             timed=True)
        player.process_batch([{"artist": "C", "song": "Tres", "file_path": "/m/3.mp3"}],
                             timed=True)

        ids = [j["batch_id"] for j in player.demucs_queue]
        assert ids[0] == ids[1] and ids[2] != ids[0]
        player.demucs_queue.clear()
        player.demucs_active = False


class TestBatchTimingDialog:
    """El resumen: tiempo por canción, total y errores aparte."""

    def _html(self, app, rows):
        dialog = BatchTimingDialog(None, rows)
        text = dialog._build_html(rows)
        dialog.deleteLater()
        return text

    def test_una_fila_por_cancion_con_su_tiempo(self, app):
        text = self._html(app, [
            {"artist": "A", "song": "Uno", "elapsed": 192, "device": "CUDA", "failed": False},
            {"artist": "B", "song": "Dos", "elapsed": 68, "device": "CUDA", "failed": False},
        ])
        assert "A - Uno" in text and "3 min 12 s" in text
        assert "B - Dos" in text and "1 min 8 s" in text
        assert "Total: 4 min 20 s" in text
        assert "Procesado con: CUDA" in text

    def test_los_que_fallaron_no_suman_al_total(self, app):
        text = self._html(app, [
            {"artist": "A", "song": "Uno", "elapsed": 60, "device": "CPU", "failed": False},
            {"artist": "B", "song": "Dos", "elapsed": 999, "device": "", "failed": True},
        ])
        assert "Total: 1 min 0 s" in text
        assert "Error" in text
        assert "1 con error" in text

    def test_lista_los_dispositivos_usados(self, app):
        text = self._html(app, [
            {"artist": "A", "song": "Uno", "elapsed": 60, "device": "MPS", "failed": False},
            {"artist": "B", "song": "Dos", "elapsed": 60, "device": "CPU", "failed": False},
        ])
        assert "Procesado con: CPU, MPS" in text

    def test_escapa_el_nombre(self, app):
        text = self._html(app, [
            {"artist": "A & <b>B</b>", "song": "Uno", "elapsed": 60,
             "device": "CPU", "failed": False},
        ])
        assert "&amp; &lt;b&gt;" in text
