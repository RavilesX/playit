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
    extract_color,
    fold_text,
    join_rows,
    load_vocals,
    parse_lrc,
    seconds_to_lrc_ts,
    sentence_case,
    split_rows,
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


def _press(widget, x, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(x, 10),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        mods,
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
        assert [round(ln.start, 2) for ln in lines] == [1.0, 3.5, 60.25]

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
        assert [round(ln.start, 2) for ln in reparsed] == [1.0, 3.5]
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


CTRL = Qt.KeyboardModifier.ControlModifier


class TestArrastreGrupal:
    """Ctrl + arrastrar un borde mueve varias líneas la misma distancia."""

    def _widget(self, from_line=True):
        lines = [LyricLine(1.0, "a"), LyricLine(5.0, "b"), LyricLine(9.0, "c")]
        w = WaveformWidget(_synthetic_audio(duration=20.0), lines)
        w.px_per_sec = 150.0
        w.start_pos = 0.0
        w.group_drag_from_line = from_line
        w.resize(3000, 240)
        return w, lines

    def test_desde_la_linea_agarrada_mueve_esa_y_las_siguientes(self, app):
        w, lines = self._widget(from_line=True)
        w.mousePressEvent(_press(w, 750, CTRL))   # borde de línea 1 (5.0s)
        w.mouseMoveEvent(_move(w, 900))           # +150px = +1.0s
        assert [round(ln.start, 2) for ln in lines] == [1.0, 6.0, 10.0]

    def test_sin_desde_el_cursor_mueve_todas(self, app):
        w, lines = self._widget(from_line=False)
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 900))
        assert [round(ln.start, 2) for ln in lines] == [2.0, 6.0, 10.0]

    def test_conserva_las_separaciones_internas(self, app):
        w, lines = self._widget(from_line=True)
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 300))           # -3.0s
        assert lines[2].start - lines[1].start == pytest.approx(4.0)

    def test_tope_contra_la_linea_que_no_se_mueve(self, app):
        w, lines = self._widget(from_line=True)
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 0))             # intenta pasar antes de 1.0s
        assert lines[1].start == pytest.approx(1.0 + lse.MIN_GAP)
        # El grupo se movió en bloque: la tercera conserva su distancia.
        assert lines[2].start == pytest.approx(5.0 + lse.MIN_GAP)

    def test_tope_en_cero_moviendo_todas(self, app):
        w, lines = self._widget(from_line=False)
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 0))
        assert lines[0].start == pytest.approx(0.0)
        assert lines[1].start == pytest.approx(4.0)

    def test_tope_al_final_de_la_pista(self, app):
        w, lines = self._widget(from_line=True)
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 2900))          # muy a la derecha
        assert lines[2].start == pytest.approx(w.audio.duration)
        assert lines[1].start == pytest.approx(w.audio.duration - 4.0)

    def test_ctrl_sobre_el_borde_no_toca_la_seleccion(self, app):
        w, _ = self._widget()
        w.selection = {0}
        w.mousePressEvent(_press(w, 750, CTRL))
        assert w.selection == {0}

    def test_soltar_limpia_el_grupo(self, app):
        w, _ = self._widget()
        w.mousePressEvent(_press(w, 750, CTRL))
        w.mouseMoveEvent(_move(w, 900))
        w.mouseReleaseEvent(None)
        assert w._drag_group == []
        # Un arrastre normal posterior mueve solo su línea.
        w.mousePressEvent(_press(w, 150))
        w.mouseMoveEvent(_move(w, 300))
        assert w.lines[0].start == pytest.approx(2.0)
        assert w.lines[1].start == pytest.approx(6.0)

    def test_arrastre_normal_no_agrupa(self, app):
        w, lines = self._widget()
        w.mousePressEvent(_press(w, 750))
        w.mouseMoveEvent(_move(w, 900))
        assert [round(ln.start, 2) for ln in lines] == [1.0, 6.0, 9.0]

    def test_el_checkbox_del_dialogo_define_el_alcance(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        assert dialog.waveform.group_drag_from_line is False
        dialog.from_cursor_chk.setChecked(True)
        assert dialog.waveform.group_drag_from_line is True


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
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.5, 5.5, 9.5]

    def test_shift_all_clamp_a_cero(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(-2.0)
        assert dialog.lines[0].start == pytest.approx(0.0)

    def test_shift_desde_cursor_solo_afecta_posteriores(self, dialog):
        dialog.from_cursor_chk.setChecked(True)
        dialog.waveform.playback_pos = 4.0
        dialog._shift_all(0.5)
        # La de 1.0s no se mueve; las de 5.0 y 9.0 sí.
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 5.5, 9.5]


class TestSentenceCase:
    def test_primera_mayuscula_resto_minusculas(self):
        assert sentence_case("HOLA MUNDO cruel") == "Hola mundo cruel"

    def test_cada_renglon_por_separado(self):
        assert sentence_case("uno\nDOS") == "Uno\nDos"

    def test_salta_signos_iniciales(self):
        assert sentence_case("¿DÓNDE estás?") == "¿Dónde estás?"

    def test_texto_sin_letras_no_falla(self):
        assert sentence_case("") == ""
        assert sentence_case("...") == "..."

    def test_acentos(self):
        assert sentence_case("ÁNGEL de la noche") == "Ángel de la noche"


class TestFormatoAutomatico:
    """El checkbox "Formato automático" de los diálogos de texto."""

    def _chk(self, dlg):
        from PyQt6.QtWidgets import QCheckBox
        return next(c for c in dlg.findChildren(QCheckBox)
                    if c.text() == "Formato automático")

    def test_activo_por_defecto(self, dialog, monkeypatch):
        capturado = {}

        def captura_exec(dlg_self):
            capturado["on"] = self._chk(dlg_self).isChecked()
            return 0

        monkeypatch.setattr(lse.QInputDialog, "exec", captura_exec)
        dialog._edit_text(0)
        assert capturado["on"] is True

    def test_desactivado_conserva_mayusculas(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        def fake_exec(dlg_self):
            self._chk(dlg_self).setChecked(False)
            dlg_self.findChild(QPlainTextEdit).setPlainText("hola MARÍA José")
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog._edit_text(0)
        assert strip_tags(dialog.lines[0].text) == "hola MARÍA José"

    def test_activado_formatea(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        def fake_exec(dlg_self):
            dlg_self.findChild(QPlainTextEdit).setPlainText("hola MARÍA José")
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog._edit_text(0)
        assert strip_tags(dialog.lines[0].text) == "Hola maría josé"

    def test_eleccion_persiste_entre_dialogos(self, dialog, monkeypatch):
        # Desactivarlo en un diálogo lo deja desactivado en el siguiente y
        # también afecta a unir líneas (que no tiene diálogo).
        monkeypatch.setattr(
            lse.QInputDialog, "exec",
            lambda dlg_self: (self._chk(dlg_self).setChecked(False), 0)[1],
        )
        dialog._edit_text(0)
        assert dialog._auto_format is False

        monkeypatch.setattr(lse.QInputDialog, "exec", lambda dlg_self: 0)
        dialog._edit_text(0)  # se reabre ya desmarcado
        assert dialog._auto_format is False

        dialog.lines[0].text = wrap_lyric("HOLA")
        dialog.waveform.selection = {0, 1}
        dialog._merge_lines()
        assert strip_tags(dialog.lines[0].text) == "HOLA dos"

    def test_checkbox_tambien_en_nueva_linea(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        def fake_exec(dlg_self):
            self._chk(dlg_self).setChecked(False)
            dlg_self.findChild(QPlainTextEdit).setPlainText("DJ Snake")
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog.waveform.playback_pos = 3.0
        dialog._add_line_with_text()
        agregada = next(ln for ln in dialog.lines if round(ln.start, 2) == 3.0)
        assert strip_tags(agregada.text) == "DJ Snake"


class TestDialogLineas:
    def test_add_line_envuelve_con_tags(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        def fake_exec(dlg_self):
            editor = dlg_self.findChild(QPlainTextEdit)
            editor.setPlainText("nueva linea")
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog.waveform.playback_pos = 3.0
        dialog._add_line_with_text()
        agregada = next(ln for ln in dialog.lines if round(ln.start, 2) == 3.0)
        # El texto se guarda con formato de oración (primera letra mayúscula).
        assert agregada.text == "<center>Nueva linea</center>"

    def test_add_line_cancelado_no_agrega(self, dialog, monkeypatch):
        monkeypatch.setattr(lse.QInputDialog, "exec", lambda dlg_self: 0)
        antes = len(dialog.lines)
        dialog._add_line_with_text()
        assert len(dialog.lines) == antes

    def test_add_line_usa_fuente_del_editor(self, dialog, monkeypatch):
        # La caja de texto lleva la fuente del editor (Space Mono).
        from PyQt6.QtWidgets import QPlainTextEdit

        capturado = {}

        def captura_exec(dlg_self):
            editor = dlg_self.findChild(QPlainTextEdit)
            capturado["css"] = editor.styleSheet() if editor else None
            return 0

        monkeypatch.setattr(lse.QInputDialog, "exec", captura_exec)
        dialog._add_line_with_text()
        assert "Space Mono" in capturado["css"]

    def test_add_line_blank_no_abre_dialogo(self, dialog, monkeypatch):
        # No debe invocar el diálogo de texto; agrega una línea vacía.
        def _boom(*a, **k):
            raise AssertionError("no debe abrir diálogo")
        monkeypatch.setattr(lse.QInputDialog, "exec", _boom)
        dialog.waveform.playback_pos = 3.0
        antes = len(dialog.lines)
        dialog._add_line_blank()
        assert len(dialog.lines) == antes + 1
        agregada = next(ln for ln in dialog.lines if round(ln.start, 2) == 3.0)
        assert agregada.text == "<center></center>"

    def test_delete_line_borra_seleccionada(self, dialog):
        dialog.waveform.selection = {1}
        dialog._delete_line()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 9.0]

    def test_delete_line_sin_seleccion_no_hace_nada(self, dialog):
        dialog.waveform.clear_selection()
        antes = len(dialog.lines)
        dialog._delete_line()
        assert len(dialog.lines) == antes

    def test_delete_multiple_borra_todas(self, dialog):
        dialog.waveform.selection = {0, 2}
        dialog._delete_line()
        assert [round(ln.start, 2) for ln in dialog.lines] == [5.0]
        assert dialog.waveform.selection == set()


class TestWaveformSeleccion:
    def _wf(self, app):
        audio = _synthetic_audio(duration=12.0, sr=8000)
        lines = [LyricLine(float(i + 1), wrap_lyric(t))
                 for i, t in enumerate(["a", "b", "c", "d"])]
        return WaveformWidget(audio, lines)

    def test_click_simple_selecciona_uno(self, app):
        wf = self._wf(app)
        wf._apply_click_selection(2, Qt.KeyboardModifier.NoModifier)
        assert wf.selection == {2}
        assert wf.selected == 2

    def test_ctrl_agrega_y_alterna(self, app):
        wf = self._wf(app)
        wf._apply_click_selection(1, Qt.KeyboardModifier.NoModifier)
        wf._apply_click_selection(3, Qt.KeyboardModifier.ControlModifier)
        assert wf.selection == {1, 3}
        # Segundo Ctrl-click sobre el mismo lo quita.
        wf._apply_click_selection(3, Qt.KeyboardModifier.ControlModifier)
        assert wf.selection == {1}

    def test_shift_selecciona_rango(self, app):
        wf = self._wf(app)
        wf._apply_click_selection(1, Qt.KeyboardModifier.NoModifier)
        wf._apply_click_selection(3, Qt.KeyboardModifier.ShiftModifier)
        assert wf.selection == {1, 2, 3}


class TestDialogUnir:
    def test_can_merge_falso_con_uno(self, dialog):
        dialog.waveform.selection = {1}
        assert dialog._can_merge() is False

    def test_can_merge_falso_no_contiguo(self, dialog):
        dialog.waveform.selection = {0, 2}
        assert dialog._can_merge() is False

    def test_can_merge_true_contiguo(self, dialog):
        dialog.waveform.selection = {0, 1, 2}
        assert dialog._can_merge() is True

    def test_merge_une_textos_y_conserva_primer_timestamp(self, dialog):
        # Líneas: 1.0/uno, 5.0/dos, 9.0/tres.
        dialog.waveform.selection = {0, 1}
        dialog._merge_lines()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 9.0]
        assert strip_tags(dialog.lines[0].text) == "Uno dos"

    def test_merge_no_contiguo_no_hace_nada(self, dialog):
        dialog.waveform.selection = {0, 2}
        antes = len(dialog.lines)
        dialog._merge_lines()
        assert len(dialog.lines) == antes

    def test_boton_unir_estado_segun_seleccion(self, dialog):
        dialog.waveform.select_single(0)
        assert dialog.merge_btn.isEnabled() is False
        dialog.waveform.selection = {0, 1}
        dialog._update_merge_state()
        assert dialog.merge_btn.isEnabled() is True


class TestDialogEditarTexto:
    def test_edit_muestra_limpio_y_guarda_envuelto(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        capturado = {}
        original = lse.QInputDialog.setTextValue

        # Espía que captura el default SIN bloquearlo: el guardado ahora lee
        # el documento del editor (colores por renglón), no textValue().
        def spy(dlg_self, t):
            capturado["default"] = t
            original(dlg_self, t)

        monkeypatch.setattr(lse.QInputDialog, "setTextValue", spy)

        def fake_exec(dlg_self):
            editor = dlg_self.findChild(QPlainTextEdit)
            editor.setPlainText("editado")
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)

        dialog._edit_text(0)
        # El default mostrado al usuario va sin tags...
        assert capturado["default"] == "uno"
        # ...pero lo guardado las re-incluye (y con formato de oración).
        assert dialog.lines[0].text == "<center>Editado</center>"

    def test_edit_fuerza_autowrap(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        capturado = {}

        def captura_exec(self):
            editor = self.findChild(QPlainTextEdit)
            capturado["wrap"] = editor.lineWrapMode() if editor else None
            return 0  # cancelar: no modifica nada

        monkeypatch.setattr(lse.QInputDialog, "exec", captura_exec)
        dialog._edit_text(0)
        assert capturado["wrap"] == QPlainTextEdit.LineWrapMode.WidgetWidth

    def test_enter_inserta_salto_dentro_de_la_linea(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QPlainTextEdit

        def fake_exec(self):
            editor = self.findChild(QPlainTextEdit)
            cur = editor.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            editor.setTextCursor(cur)
            editor.insertPlainText("\nsegunda")  # Enter + texto
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog._edit_text(0)
        # El salto queda dentro de la misma línea (no crea otra LyricLine);
        # cada renglón lleva su propia mayúscula inicial.
        assert dialog.lines[0].text == "<center>Uno\nSegunda</center>"
        assert len(dialog.lines) == 3

    def test_salto_de_linea_roundtrip_lrc(self, dialog, tmp_path):
        # El \n se guarda como línea de continuación y se re-parsea igual.
        dialog.lines[0].text = wrap_lyric("uno\nsegunda")
        p = tmp_path / "out.lrc"
        write_lrc(p, dialog.lines)
        reparsed = parse_lrc(p)
        assert reparsed[0].text == "<center>uno\nsegunda</center>"

    def test_separar_linea_divide_en_el_cursor(self, dialog, monkeypatch):
        from PyQt6.QtWidgets import QDialogButtonBox, QPlainTextEdit

        # Línea 0: "uno" en 1.0s. Cursor de reproducción en 2.5s.
        dialog.lines[0].text = wrap_lyric("hola mundo")
        dialog.waveform.playback_pos = 2.5
        n_antes = len(dialog.lines)

        def fake_exec(self):
            editor = self.findChild(QPlainTextEdit)
            # Coloca el cursor tras "hola " (posición 5) y dispara Separar.
            cur = editor.textCursor()
            cur.setPosition(5)
            editor.setTextCursor(cur)
            bbox = self.findChild(QDialogButtonBox)
            split_btn = next(
                b for b in bbox.buttons() if b.text() == "Separar línea"
            )
            split_btn.click()
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog._edit_text(0)

        # Se agregó una línea.
        assert len(dialog.lines) == n_antes + 1
        # Línea actual conserva lo de antes del cursor (con trim).
        actual = next(ln for ln in dialog.lines if ln.start == 1.0)
        assert strip_tags(actual.text) == "Hola"
        # Nueva línea: texto tras el cursor, timestamp en el cursor de play.
        nueva = next(ln for ln in dialog.lines if ln.start == 2.5)
        assert strip_tags(nueva.text) == "Mundo"


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


class TestDialogDeshacer:
    def test_undo_revierte_shift(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        dialog._undo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 5.0, 9.0]

    def test_undo_revierte_delete(self, dialog):
        dialog.waveform.selection = {1}
        dialog._delete_line()
        dialog._undo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 5.0, 9.0]
        assert strip_tags(dialog.lines[1].text) == "dos"

    def test_undo_revierte_agregar(self, dialog):
        dialog.waveform.playback_pos = 3.0
        dialog._add_line_blank()
        assert len(dialog.lines) == 4
        dialog._undo()
        assert len(dialog.lines) == 3

    def test_undo_revierte_merge(self, dialog):
        dialog.waveform.selection = {0, 1}
        dialog._merge_lines()
        dialog._undo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 5.0, 9.0]
        assert strip_tags(dialog.lines[0].text) == "uno"

    def test_undo_revierte_color(self, dialog):
        dialog.waveform.selection = {0}
        dialog._apply_color("azul")
        assert extract_color(dialog.lines[0].text) == "azul"
        dialog._undo()
        assert extract_color(dialog.lines[0].text) is None

    def test_undo_revierte_arrastre(self, dialog):
        # El agarre del borde emite drag_started, que empuja el snapshot.
        dialog.waveform.drag_started.emit()
        dialog.lines[0].start = 2.0
        dialog._undo()
        assert dialog.lines[0].start == pytest.approx(1.0)

    def test_undo_descarta_snapshots_sin_cambio(self, dialog):
        # Agarrar un borde sin moverlo deja un snapshot igual al estado:
        # el Ctrl+Z siguiente debe saltárselo y deshacer el cambio real.
        dialog.waveform.selection = {1}
        dialog._delete_line()
        dialog._push_undo()  # snapshot redundante (sin mutación después)
        dialog._undo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 5.0, 9.0]

    def test_undo_multiple_en_orden_inverso(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        dialog._shift_all(0.5)
        dialog._undo()
        assert round(dialog.lines[0].start, 2) == 1.5
        dialog._undo()
        assert round(dialog.lines[0].start, 2) == 1.0

    def test_undo_sin_historial_no_hace_nada(self, dialog):
        antes = dialog._snapshot()
        dialog._undo()
        assert dialog._snapshot() == antes

    def test_undo_limpia_seleccion(self, dialog):
        dialog.waveform.selection = {0, 2}
        dialog._delete_line()
        dialog._undo()
        assert dialog.waveform.selection == set()

    def test_undo_hasta_original_sin_cambios(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        assert dialog._has_changes() is True
        dialog._undo()
        assert dialog._has_changes() is False


class TestDialogRehacer:
    def test_redo_reaplica_lo_deshecho(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        dialog._undo()
        dialog._redo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.5, 5.5, 9.5]

    def test_redo_restaura_linea_borrada_y_reborra(self, dialog):
        dialog.waveform.selection = {1}
        dialog._delete_line()
        dialog._undo()
        assert len(dialog.lines) == 3
        dialog._redo()
        assert [round(ln.start, 2) for ln in dialog.lines] == [1.0, 9.0]

    def test_mutacion_nueva_invalida_redo(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        dialog._undo()
        dialog.waveform.selection = {0}
        dialog._apply_color("azul")  # mutación nueva → redo vacío
        dialog._redo()
        assert extract_color(dialog.lines[0].text) == "azul"  # no cambió nada
        assert round(dialog.lines[0].start, 2) == 1.0

    def test_redo_sin_historial_no_hace_nada(self, dialog):
        antes = dialog._snapshot()
        dialog._redo()
        assert dialog._snapshot() == antes

    def test_ciclo_undo_redo_multiple(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)   # 1.5
        dialog._shift_all(0.5)   # 2.0
        dialog._undo()
        dialog._undo()
        assert round(dialog.lines[0].start, 2) == 1.0
        dialog._redo()
        assert round(dialog.lines[0].start, 2) == 1.5
        dialog._redo()
        assert round(dialog.lines[0].start, 2) == 2.0
        dialog._redo()  # historial agotado: no-op
        assert round(dialog.lines[0].start, 2) == 2.0

    def test_undo_tras_redo_vuelve_a_deshacer(self, dialog):
        dialog.from_cursor_chk.setChecked(False)
        dialog._shift_all(0.5)
        dialog._undo()
        dialog._redo()
        dialog._undo()
        assert round(dialog.lines[0].start, 2) == 1.0


class TestRenglonesColoreados:
    AZUL = '<center>uno\n<font color="#3AABEF">dos</font></center>'
    # Igual, pero como queda tras pasar por el diálogo (formato de oración).
    AZUL_CAP = '<center>Uno\n<font color="#3AABEF">Dos</font></center>'

    def test_split_rows_formato_clasico_hereda_color(self):
        t = wrap_lyric("uno\ndos", "azul")
        assert split_rows(t) == [("uno", "azul"), ("dos", "azul")]

    def test_split_rows_sin_color(self):
        assert split_rows("<center>uno\ndos</center>") == [
            ("uno", None), ("dos", None)]

    def test_split_rows_color_por_renglon(self):
        assert split_rows(self.AZUL) == [("uno", None), ("dos", "azul")]

    def test_join_rows_homogeneo_usa_formato_clasico(self):
        assert join_rows([("uno", None), ("dos", None)]) == \
            "<center>uno\ndos</center>"
        assert join_rows([("uno", "azul"), ("dos", "azul")]) == \
            wrap_lyric("uno\ndos", "azul")

    def test_join_rows_mixto_etiqueta_por_renglon(self):
        assert join_rows([("uno", None), ("dos", "azul")]) == self.AZUL

    def test_roundtrip_mixto(self):
        assert join_rows(split_rows(self.AZUL)) == self.AZUL

    def test_roundtrip_lrc_en_disco(self, tmp_path):
        p = tmp_path / "out.lrc"
        write_lrc(p, [LyricLine(1.0, self.AZUL)])
        assert parse_lrc(p)[0].text == self.AZUL

    def test_extract_color_devuelve_primer_color(self):
        assert extract_color(self.AZUL) == "azul"

    def _edit(self, dialog, monkeypatch, manipulate):
        from PyQt6.QtWidgets import QDialogButtonBox, QPlainTextEdit

        def fake_exec(dlg_self):
            editor = dlg_self.findChild(QPlainTextEdit)
            bbox = dlg_self.findChild(QDialogButtonBox)
            manipulate(editor, bbox)
            return 1

        monkeypatch.setattr(lse.QInputDialog, "exec", fake_exec)
        dialog._edit_text(0)

    def test_dialogo_colorea_solo_renglon_del_cursor(self, dialog, monkeypatch):
        dialog.lines[0].text = wrap_lyric("uno\ndos")

        def manipulate(editor, bbox):
            cur = editor.textCursor()
            cur.movePosition(cur.MoveOperation.End)  # renglón 2
            editor.setTextCursor(cur)
            azul = next(b for b in bbox.buttons()
                        if b.toolTip().startswith("Azul"))
            azul.click()

        self._edit(dialog, monkeypatch, manipulate)
        assert dialog.lines[0].text == self.AZUL_CAP

    def test_dialogo_toggle_regresa_a_default(self, dialog, monkeypatch):
        dialog.lines[0].text = self.AZUL

        def manipulate(editor, bbox):
            cur = editor.textCursor()
            cur.movePosition(cur.MoveOperation.End)  # renglón 2 (azul)
            editor.setTextCursor(cur)
            azul = next(b for b in bbox.buttons()
                        if b.toolTip().startswith("Azul"))
            azul.click()  # ya era azul → vuelve a default

        self._edit(dialog, monkeypatch, manipulate)
        assert dialog.lines[0].text == "<center>Uno\nDos</center>"

    def test_dialogo_conserva_colores_existentes(self, dialog, monkeypatch):
        dialog.lines[0].text = self.AZUL
        self._edit(dialog, monkeypatch, lambda editor, bbox: None)
        assert dialog.lines[0].text == self.AZUL_CAP


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

    def test_focus_search_enfoca_y_selecciona(self, dialog):
        dialog.search_box.setText("hola")
        dialog._focus_search()
        assert dialog.focusWidget() is dialog.search_box
        assert dialog.search_box.selectedText() == "hola"

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

    def test_busqueda_atraviesa_saltos_de_linea(self, dialog):
        self._set_lines(dialog, ["hola\nmundo", "otra"])
        dialog.search_box.setText("hola mundo")
        dialog._search_next()
        assert dialog._search_index == 0
