"""Tests del editor de sincronización por onda (lyrics_sync_editor).

Cubren: parseo/escritura LRC, helpers de tags, generación de peaks (fix de
drift), mapeo tiempo↔pixel y hit-testing del widget de onda, arrastre del
borde con sus topes, y las acciones del diálogo (agregar, borrar, editar
texto, offset global y offset desde el cursor).

Headless (QT_QPA_PLATFORM=offscreen). No requieren red. El audio se genera
sintéticamente con soundfile en archivos temporales.
"""

import numpy as np
import pytest
import soundfile as sf
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

import lyrics_sync_editor as lse
from lyrics_sync_editor import (
    LyricLine,
    LyricsSyncDialog,
    VocalsAudio,
    WaveformWidget,
    fold_text,
    load_vocals,
    parse_lrc,
    seconds_to_lrc_ts,
    strip_tags,
    wrap_lyric,
    write_lrc,
)

LRC_EJEMPLO = """[00:01.00]<center>Primera</center>
[00:03.50]<center>Segunda</center>
continuación
[01:00.25]<center>Tercera</center>
"""


def _make_wav(path, sr=8000, seconds=4.0):
    """Crea un wav sintético (ruido suave) para alimentar load_vocals."""
    n = int(sr * seconds)
    data = (np.sin(np.linspace(0, 200 * np.pi, n)) * 0.3).astype(np.float32)
    sf.write(str(path), data, sr)
    return path


def _synthetic_audio(duration=10.0, sr=8000):
    """VocalsAudio en memoria, sin tocar disco."""
    n = int(duration * sr)
    return VocalsAudio(
        samples=np.zeros(n, dtype=np.float32),
        sr=sr,
        duration=duration,
        peaks=np.zeros((int(duration * 200), 2), dtype=np.float32),
        peaks_per_second=200.0,
    )


def _press(widget, x):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(x, 10),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _move(widget, x):
    return QMouseEvent(
        QEvent.Type.MouseMove, QPointF(x, 10),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


# ──────────────────────────────────────────────────────────────────────
# Parseo y escritura LRC
# ──────────────────────────────────────────────────────────────────────
class TestParseLRC:
    def test_parsea_timestamps_y_ordena(self, tmp_path):
        p = tmp_path / "lyrics.lrc"
        p.write_text(LRC_EJEMPLO, encoding="utf-8")
        lines = parse_lrc(p)
        assert [round(l.start, 2) for l in lines] == [1.0, 3.5, 60.25]

    def test_anexa_lineas_sin_timestamp_al_bloque(self, tmp_path):
        p = tmp_path / "lyrics.lrc"
        p.write_text(LRC_EJEMPLO, encoding="utf-8")
        lines = parse_lrc(p)
        assert "continuación" in lines[1].text
        assert "\n" in lines[1].text

    def test_ignora_texto_antes_del_primer_timestamp(self, tmp_path):
        p = tmp_path / "lyrics.lrc"
        p.write_text("basura sin ts\n[00:02.00]real\n", encoding="utf-8")
        lines = parse_lrc(p)
        assert len(lines) == 1
        assert lines[0].text == "real"


class TestFormatoYEscritura:
    def test_seconds_to_lrc_ts_centisegundos(self):
        assert seconds_to_lrc_ts(10.5) == "00:10.50"
        assert seconds_to_lrc_ts(119.80) == "01:59.80"
        assert seconds_to_lrc_ts(60.25) == "01:00.25"

    def test_seconds_to_lrc_ts_no_negativo(self):
        assert seconds_to_lrc_ts(-3.0) == "00:00.00"

    def test_write_lrc_roundtrip(self, tmp_path):
        p = tmp_path / "lyrics.lrc"
        original = [
            LyricLine(1.0, "<center>A</center>"),
            LyricLine(3.5, "<center>B</center>\nsegunda"),
        ]
        write_lrc(p, original)
        reparsed = parse_lrc(p)
        assert [round(l.start, 2) for l in reparsed] == [1.0, 3.5]
        assert reparsed[1].text == "<center>B</center>\nsegunda"

    def test_write_lrc_ordena_por_inicio(self, tmp_path):
        p = tmp_path / "lyrics.lrc"
        write_lrc(p, [LyricLine(5.0, "tarde"), LyricLine(1.0, "antes")])
        content = p.read_text(encoding="utf-8")
        assert content.index("antes") < content.index("tarde")


# ──────────────────────────────────────────────────────────────────────
# Tags HTML
# ──────────────────────────────────────────────────────────────────────
class TestTags:
    def test_strip_tags_quita_html(self):
        assert strip_tags("<center>Hola</center>") == "Hola"
        assert strip_tags("sin tags") == "sin tags"

    def test_wrap_lyric_envuelve(self):
        assert wrap_lyric("Hola") == "<center>Hola</center>"

    def test_strip_y_wrap_son_inversos_para_center(self):
        assert wrap_lyric(strip_tags("<center>X</center>")) == "<center>X</center>"


# ──────────────────────────────────────────────────────────────────────
# Generación de peaks (fix de drift)
# ──────────────────────────────────────────────────────────────────────
class TestLoadVocals:
    def test_peaks_per_second_es_real_no_nominal(self, tmp_path):
        # sr=44100, win=int(44100/200)=220 -> pps real = 44100/220, no 200.
        _make_wav(tmp_path / "v.wav", sr=44100, seconds=0.5)
        audio = load_vocals(tmp_path / "v.wav")
        win = int(44100 / lse.PEAKS_PER_SECOND)
        assert audio.peaks_per_second == pytest.approx(44100 / win)
        assert audio.peaks_per_second != 200.0

    def test_duracion_y_forma_de_peaks(self, tmp_path):
        _make_wav(tmp_path / "v.wav", sr=8000, seconds=2.0)
        audio = load_vocals(tmp_path / "v.wav")
        assert audio.duration == pytest.approx(2.0, abs=0.01)
        assert audio.peaks.shape[1] == 2
        assert audio.sr == 8000


# ──────────────────────────────────────────────────────────────────────
# Widget de onda: mapeo y hit-testing
# ──────────────────────────────────────────────────────────────────────
class TestWaveformMapeo:
    def test_sec_to_x_y_x_to_sec_son_inversos(self, app):
        w = WaveformWidget(_synthetic_audio(), [])
        w.px_per_sec = 150.0
        w.start_pos = 0.0
        assert w.sec_to_x(2.0) == 300.0
        assert w.x_to_sec(300.0) == 2.0

    def test_mapeo_respeta_start_pos(self, app):
        w = WaveformWidget(_synthetic_audio(), [])
        w.px_per_sec = 100.0
        w.start_pos = 5.0
        assert w.sec_to_x(5.0) == 0.0
        assert w.x_to_sec(0.0) == 5.0

    def test_edge_at_detecta_inicio(self, app):
        lines = [LyricLine(1.0, "a"), LyricLine(5.0, "b")]
        w = WaveformWidget(_synthetic_audio(), lines)
        w.px_per_sec = 150.0
        w.start_pos = 0.0
        assert w._edge_at(150) == 0       # inicio de línea 0 -> x=150
        assert w._edge_at(154) == 0       # dentro del margen de 6px
        assert w._edge_at(200) is None    # lejos de cualquier borde

    def test_block_at_detecta_bloque(self, app):
        lines = [LyricLine(1.0, "a"), LyricLine(5.0, "b")]
        w = WaveformWidget(_synthetic_audio(), lines)
        w.px_per_sec = 150.0
        w.start_pos = 0.0
        assert w._block_at(300) == 0      # entre 1.0s(x150) y 5.0s(x750)
        assert w._block_at(800) == 1


class TestWaveformArrastre:
    def _widget(self):
        lines = [LyricLine(1.0, "a"), LyricLine(5.0, "b")]
        w = WaveformWidget(_synthetic_audio(duration=20.0), lines)
        w.px_per_sec = 150.0
        w.start_pos = 0.0
        w.resize(1500, 240)
        return w, lines

    def test_arrastra_inicio_y_actualiza(self, app):
        w, lines = self._widget()
        w.mousePressEvent(_press(w, 150))   # agarra borde de línea 0
        w.mouseMoveEvent(_move(w, 300))     # +150px = +1.0s
        assert lines[0].start == pytest.approx(2.0)

    def test_tope_no_cruza_linea_siguiente(self, app):
        w, lines = self._widget()
        w.mousePressEvent(_press(w, 150))
        w.mouseMoveEvent(_move(w, 1200))    # intenta pasar 5.0s
        assert lines[0].start == pytest.approx(5.0 - lse.MIN_GAP)

    def test_tope_no_cruza_linea_anterior(self, app):
        w, lines = self._widget()
        w.mousePressEvent(_press(w, 750))   # borde de línea 1 (5.0s -> x750)
        w.mouseMoveEvent(_move(w, 50))      # intenta ir antes de 1.0s
        assert lines[1].start == pytest.approx(1.0 + lse.MIN_GAP)


# ──────────────────────────────────────────────────────────────────────
# Diálogo: acciones de edición
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def dialog(app, tmp_path):
    _make_wav(tmp_path / "vocals.wav", sr=8000, seconds=12.0)
    lrc = tmp_path / "lyrics.lrc"
    lrc.write_text(
        "[00:01.00]<center>uno</center>\n"
        "[00:05.00]<center>dos</center>\n"
        "[00:09.00]<center>tres</center>\n",
        encoding="utf-8",
    )
    dlg = LyricsSyncDialog(None, tmp_path / "vocals.wav", lrc)
    yield dlg
    dlg._timer.stop()
    dlg.player.stop()


class TestDialogShift:
    def test_shift_all_desplaza_todo(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        assert [round(l.start, 2) for l in dialog.lines] == [1.5, 5.5, 9.5]

    def test_shift_all_clamp_a_cero(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(-2.0)
        assert dialog.lines[0].start == pytest.approx(0.0)

    def test_shift_desde_cursor_solo_afecta_posteriores(self, dialog):
        dialog.from_cursor_chk.setChecked(True)
        dialog.waveform.playback_pos = 4.0
        dialog._shift_all(0.5)
        # La de 1.0s no se mueve; las de 5.0 y 9.0 sí.
        assert [round(l.start, 2) for l in dialog.lines] == [1.0, 5.5, 9.5]


class TestDialogLineas:
    def test_add_line_envuelve_con_tags(self, dialog, monkeypatch):
        monkeypatch.setattr(
            lse.QInputDialog, "getMultiLineText",
            staticmethod(lambda *a, **k: ("nueva linea", True)),
        )
        dialog.waveform.playback_pos = 3.0
        dialog._add_line()
        agregada = next(l for l in dialog.lines if round(l.start, 2) == 3.0)
        assert agregada.text == "<center>nueva linea</center>"

    def test_add_line_cancelado_no_agrega(self, dialog, monkeypatch):
        monkeypatch.setattr(
            lse.QInputDialog, "getMultiLineText",
            staticmethod(lambda *a, **k: ("", False)),
        )
        antes = len(dialog.lines)
        dialog._add_line()
        assert len(dialog.lines) == antes

    def test_delete_line_borra_seleccionada(self, dialog):
        dialog.waveform.selected = 1
        dialog._delete_line()
        assert [round(l.start, 2) for l in dialog.lines] == [1.0, 9.0]

    def test_delete_line_sin_seleccion_no_hace_nada(self, dialog):
        dialog.waveform.selected = -1
        antes = len(dialog.lines)
        dialog._delete_line()
        assert len(dialog.lines) == antes


class TestDialogEditarTexto:
    def test_edit_muestra_limpio_y_guarda_envuelto(self, dialog, monkeypatch):
        capturado = {}

        def fake(parent, title, label, text, *a, **k):
            capturado["default"] = text
            return ("editado", True)

        monkeypatch.setattr(
            lse.QInputDialog, "getMultiLineText", staticmethod(fake),
        )
        dialog._edit_text(0)
        # El default mostrado al usuario va sin tags...
        assert capturado["default"] == "uno"
        # ...pero lo guardado las re-incluye.
        assert dialog.lines[0].text == "<center>editado</center>"


def _patch_confirm(monkeypatch, respuesta):
    """Mockea styled_message_box para que devuelva Yes o No sin abrir modal."""
    from PyQt6.QtWidgets import QMessageBox
    valor = (QMessageBox.StandardButton.Yes if respuesta
             else QMessageBox.StandardButton.No)
    monkeypatch.setattr(lse, "styled_message_box", lambda *a, **k: valor)
    return valor


class TestDialogGuardar:
    def test_save_con_cambios_confirmado_escribe(self, dialog, monkeypatch):
        _patch_confirm(monkeypatch, True)
        dialog.lines[0].start = 2.0
        dialog._save()
        assert dialog.saved is True
        content = dialog._lrc_path.read_text(encoding="utf-8")
        assert "[00:02.00]<center>uno</center>" in content

    def test_save_con_cambios_rechazado_no_escribe(self, dialog, monkeypatch):
        _patch_confirm(monkeypatch, False)
        original = dialog._lrc_path.read_text(encoding="utf-8")
        dialog.lines[0].start = 2.0
        dialog._save()
        assert dialog.saved is False
        assert dialog._lrc_path.read_text(encoding="utf-8") == original

    def test_save_sin_cambios_no_pide_confirmacion(self, dialog, monkeypatch):
        # Si pidiera confirmación, el lambda fallaría el test al ser llamado.
        monkeypatch.setattr(
            lse, "styled_message_box",
            lambda *a, **k: pytest.fail("No debe confirmar sin cambios"),
        )
        dialog._save()  # sin tocar nada
        assert dialog.saved is False


class TestDialogConfirmarCancelar:
    def test_cancelar_sin_cambios_no_confirma(self, dialog, monkeypatch):
        monkeypatch.setattr(
            lse, "styled_message_box",
            lambda *a, **k: pytest.fail("No debe confirmar sin cambios"),
        )
        dialog.reject()
        assert dialog._has_changes() is False

    def test_has_changes_detecta_modificacion(self, dialog):
        assert dialog._has_changes() is False
        dialog.lines[0].start += 0.5
        assert dialog._has_changes() is True


class TestFoldText:
    def test_quita_tildes_y_baja_caja(self):
        assert fold_text("Canción") == "cancion"
        assert fold_text("ADIÓS") == "adios"

    def test_equivalencia_con_y_sin_tilde(self):
        assert fold_text("canción") == fold_text("cancion")

    def test_varias_marcas(self):
        assert fold_text("Mañanaúér") == "mananauer"


class TestDialogBuscador:
    def _set_lines(self, dialog, textos):
        dialog.lines = [
            LyricLine(float(i + 1), wrap_lyric(t)) for i, t in enumerate(textos)
        ]
        dialog.waveform.lines = dialog.lines
        dialog._search_index = -1

    def test_enter_salta_a_primera_coincidencia(self, dialog):
        self._set_lines(dialog, ["hola sol", "hola luna", "adios"])
        dialog.search_box.setText("luna")
        dialog._search_next()
        assert dialog._search_index == 1
        assert dialog.waveform.selected == 1

    def test_enter_recorre_en_bucle(self, dialog):
        self._set_lines(dialog, ["hola sol", "hola luna", "adios"])
        dialog.search_box.setText("hola")
        dialog._search_next()
        assert dialog._search_index == 0
        dialog._search_next()
        assert dialog._search_index == 1
        # Tras la última coincidencia vuelve a la primera.
        dialog._search_next()
        assert dialog._search_index == 0

    def test_sin_coincidencia_pinta_rojo(self, dialog):
        self._set_lines(dialog, ["hola", "mundo"])
        dialog.search_box.setText("zzz")
        dialog._search_next()
        assert dialog.search_box.styleSheet() == dialog._SEARCH_RED
        assert dialog._search_index == -1

    def test_coincidencia_restaura_estilo_normal(self, dialog):
        self._set_lines(dialog, ["hola"])
        dialog.search_box.setText("zzz")
        dialog._search_next()
        assert dialog.search_box.styleSheet() == dialog._SEARCH_RED
        dialog.search_box.setText("hola")
        dialog._search_next()
        assert dialog.search_box.styleSheet() == dialog._SEARCH_NORMAL

    def test_acento_busca_termino_sin_tilde_encuentra_con_tilde(self, dialog):
        self._set_lines(dialog, ["Mi canción favorita", "otra cosa"])
        dialog.search_box.setText("cancion")
        dialog._search_next()
        assert dialog._search_index == 0

    def test_acento_busca_termino_con_tilde_encuentra_sin_tilde(self, dialog):
        self._set_lines(dialog, ["otra cosa", "una cancion simple"])
        dialog.search_box.setText("canción")
        dialog._search_next()
        assert dialog._search_index == 1

    def test_cambiar_texto_reinicia_indice(self, dialog):
        self._set_lines(dialog, ["hola sol", "hola luna"])
        dialog.search_box.setText("hola")
        dialog._search_next()
        assert dialog._search_index == 0
        # textChanged dispara el reinicio del ciclo.
        dialog.search_box.setText("hola luna")
        assert dialog._search_index == -1

    def test_termino_vacio_no_marca_rojo(self, dialog):
        self._set_lines(dialog, ["hola"])
        dialog.search_box.setText("   ")
        dialog._search_next()
        assert dialog.search_box.styleSheet() == dialog._SEARCH_NORMAL
