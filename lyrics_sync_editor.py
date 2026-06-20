# PlayIt - Reproductor de audio de escritorio con separación de pistas
# Copyright (C) 2025-2026  Ricardo Aviles Sanders
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Editor de sincronización de lyrics basado en forma de onda.

Abre una ventana aparte que dibuja la onda de la voz (vocals.mp3) y los
bloques de cada línea del archivo .lrc. El usuario arrastra el inicio de
cada línea sobre la onda para corregir la sincronización línea por línea,
sin afectar las partes ya correctas (a diferencia del offset global).

Diseño modular:
  - load_vocals()      : genera los peaks de la onda (función pura).
  - MiniVocalsPlayer   : reproduce solo la voz desde una posición dada.
  - WaveformWidget     : dibuja la onda + bloques y maneja arrastre/scroll.
  - LyricsSyncDialog   : compone todo con el estilo de la app (BaseDialog).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
import soundfile as sf
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from dialogs import BaseDialog
from resources import style_url, styled_message_box
from ui_components import SizeGrip

# Sin límite superior de tamaño (permite maximizar / agrandar libremente).
_QWIDGETSIZE_MAX = 16777215

# ──────────────────────────────────────────────────────────────────────
# Constantes de configuración
# ──────────────────────────────────────────────────────────────────────
PEAKS_PER_SECOND = 200      # resolución de los peaks precalculados
DEFAULT_PX_PER_SEC = 150    # escala horizontal fija (zoom queda como variable)
EDGE_GRAB_PX = 6            # margen en px para "agarrar" el inicio de una línea
MIN_GAP = 0.05             # separación mínima en segundos entre líneas
WHEEL_SCROLL_SECONDS = 0.6  # cuánto desplaza la rueda del mouse por muesca

# Regex del timestamp LRC: [mm:ss.xx]
_LRC_TS = re.compile(r'\[(\d+):(\d+\.\d+)\]')
# Etiquetas HTML (p.ej. <center>) presentes en el .lrc; se ocultan al mostrar
# el texto sobre la onda, pero se conservan en el archivo al guardar.
_HTML_TAG = re.compile(r'<[^>]+>')


# ──────────────────────────────────────────────────────────────────────
# Modelo de datos
# ──────────────────────────────────────────────────────────────────────
@dataclass
class VocalsAudio:
    """Audio de la voz ya cargado y resumido en peaks para dibujar."""

    samples: np.ndarray     # mono, float32
    sr: int                 # sample rate
    duration: float         # segundos
    peaks: np.ndarray       # shape (n, 2): [min, max] por ventana
    peaks_per_second: float


@dataclass
class LyricLine:
    """Una línea de la letra: solo inicio (LRC puro) + texto."""

    start: float
    text: str


# ──────────────────────────────────────────────────────────────────────
# Carga de audio / generación de peaks (funciones puras)
# ──────────────────────────────────────────────────────────────────────
def load_vocals(path) -> VocalsAudio:
    """Carga vocals.mp3 a mono y precalcula peaks min/max por ventana.

    Resumir a ~PEAKS_PER_SECOND valores por segundo mantiene el repintado
    barato aun en canciones largas.
    """
    data, sr = sf.read(str(path), dtype='float32', always_2d=True)
    mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]

    win = max(1, int(sr / PEAKS_PER_SECOND))
    n = len(mono) // win
    if n == 0:
        peaks = np.zeros((1, 2), dtype=np.float32)
    else:
        block = mono[:n * win].reshape(n, win)
        peaks = np.empty((n, 2), dtype=np.float32)
        peaks[:, 0] = block.min(axis=1)
        peaks[:, 1] = block.max(axis=1)

    return VocalsAudio(
        samples=mono,
        sr=sr,
        duration=len(mono) / sr if sr else 0.0,
        peaks=peaks,
        # Resolución REAL: int(sr/200) redondea, así que sr/win != 200 exacto.
        # Usar el nominal causaba drift acumulado entre onda y audio.
        peaks_per_second=sr / win,
    )


def parse_lrc(path) -> list[LyricLine]:
    """Lee un .lrc y devuelve las líneas con timestamp (ordenadas).

    Las líneas sin timestamp se anexan al bloque actual (texto multilínea),
    igual que hace el parser principal de la app.
    """
    lines: list[LyricLine] = []
    current_start: float | None = None
    current_text: list[str] = []

    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = _LRC_TS.match(line)
            if m:
                if current_start is not None and current_text:
                    lines.append(LyricLine(current_start, '\n'.join(current_text)))
                current_start = int(m.group(1)) * 60 + float(m.group(2))
                current_text = [line[m.end():]]
            elif current_start is not None and line.strip():
                current_text.append(line)

    if current_start is not None and current_text:
        lines.append(LyricLine(current_start, '\n'.join(current_text)))

    lines.sort(key=lambda l: l.start)
    return lines


def strip_tags(text: str) -> str:
    """Quita etiquetas HTML (<center>…) para mostrar texto limpio al usuario."""
    return _HTML_TAG.sub('', text)


def wrap_lyric(text: str) -> str:
    """Envuelve el texto del usuario con las etiquetas que espera el .lrc."""
    return f'<center>{text}</center>'


def seconds_to_lrc_ts(seconds: float) -> str:
    """Convierte segundos a [mm:ss.cc] usando centisegundos enteros.

    Mismo criterio que adjust_lyrics_timing en audio_player: aritmética
    entera para evitar errores de redondeo de float.
    """
    total_cs = max(0, round(seconds * 100))
    m, rem = divmod(total_cs, 6000)
    s, c = divmod(rem, 100)
    return f"{m:02d}:{s:02d}.{c:02d}"


def write_lrc(path, lines: list[LyricLine]) -> None:
    """Reescribe el .lrc con las líneas (ordenadas por inicio)."""
    ordered = sorted(lines, key=lambda l: l.start)
    with open(path, 'w', encoding='utf-8') as f:
        for line in ordered:
            parts = line.text.split('\n')
            f.write(f"[{seconds_to_lrc_ts(line.start)}]{parts[0]}\n")
            for extra in parts[1:]:
                f.write(f"{extra}\n")


# ──────────────────────────────────────────────────────────────────────
# Mini reproductor (solo voz)
# ──────────────────────────────────────────────────────────────────────
class MiniVocalsPlayer:
    """Reproduce únicamente la voz desde una posición, en su propio hilo.

    Sigue el mismo patrón que el reproductor principal (OutputStream +
    hilo escritor) pero en mono y sin mezcla de stems.
    """

    def __init__(self, audio: VocalsAudio):
        self.audio = audio
        self._stream: sd.OutputStream | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._pos_frame = 0
        self.playing = False

    @property
    def position(self) -> float:
        return self._pos_frame / self.audio.sr if self.audio.sr else 0.0

    def play(self, start_seconds: float) -> None:
        self.stop()
        self._pos_frame = int(max(0.0, start_seconds) * self.audio.sr)
        self._cancel = threading.Event()
        self._stream = sd.OutputStream(
            samplerate=self.audio.sr, channels=1, dtype='float32',
        )
        self._stream.start()
        self.playing = True
        self._thread = threading.Thread(target=self._writer, daemon=True)
        self._thread.start()

    def _writer(self) -> None:
        chunk = 1024
        samples = self.audio.samples
        total = len(samples)
        while self._pos_frame < total:
            if self._cancel.is_set():
                break
            end = min(self._pos_frame + chunk, total)
            block = samples[self._pos_frame:end].reshape(-1, 1)
            try:
                self._stream.write(block)
            except Exception:
                break
            self._pos_frame = end
        self.playing = False

    def stop(self) -> None:
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.playing = False


# ──────────────────────────────────────────────────────────────────────
# Widget de forma de onda
# ──────────────────────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    """Dibuja la onda de la voz + bloques de líneas y maneja interacción.

    Mapeo tiempo↔pixel (estilo Subtitle Edit, simplificado a px/seg):
        x = (t - start_pos) * px_per_sec
        t = start_pos + x / px_per_sec
    """

    line_selected = pyqtSignal(int)          # índice de línea seleccionada
    line_changed = pyqtSignal(int)           # índice cuyo inicio se editó
    edit_text_requested = pyqtSignal(int)    # doble-click sobre un bloque
    seek_requested = pyqtSignal(float)       # click pide reposicionar cursor
    view_changed = pyqtSignal()              # cambió start_pos (sincroniza scrollbar)

    # Colores (estilo de la captura de Subtitle Edit)
    _C_BG = QColor(18, 22, 22)
    _C_GRID = QColor(40, 50, 50)
    _C_WAVE = QColor(0xC0, 0x4A, 0xD6)
    _C_BLOCK = QColor(120, 200, 255, 40)
    _C_BLOCK_SEL = QColor(255, 180, 60, 60)
    _C_EDGE = QColor(0xC0, 0x4A, 0xD6)
    _C_CURSOR = QColor(80, 220, 255)
    _C_TEXT = QColor(220, 220, 220)

    def __init__(self, audio: VocalsAudio, lines: list[LyricLine], parent=None):
        super().__init__(parent)
        self.audio = audio
        self.lines = lines
        self.px_per_sec = float(DEFAULT_PX_PER_SEC)
        self.start_pos = 0.0
        self.playback_pos = 0.0
        self.selected = -1

        self._drag_index: int | None = None
        self._drag_orig = 0.0
        self._drag_start_x = 0

        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── Mapeo tiempo/pixel ─────────────────────────────────────────────
    def sec_to_x(self, t: float) -> float:
        return (t - self.start_pos) * self.px_per_sec

    def x_to_sec(self, x: float) -> float:
        return self.start_pos + x / self.px_per_sec

    @property
    def visible_seconds(self) -> float:
        w = self.width()
        return w / self.px_per_sec if w > 0 else 0.0

    @property
    def max_start(self) -> float:
        return max(0.0, self.audio.duration - self.visible_seconds)

    def set_start_pos(self, seconds: float, *, emit: bool = True) -> None:
        seconds = min(max(0.0, seconds), self.max_start)
        if seconds != self.start_pos:
            self.start_pos = seconds
            if emit:
                self.view_changed.emit()
            self.update()

    def set_playback_pos(self, seconds: float) -> None:
        self.playback_pos = seconds
        # Auto-scroll: si el cursor sale de la vista, recentra.
        if seconds < self.start_pos or seconds > self.start_pos + self.visible_seconds:
            self.set_start_pos(seconds - self.visible_seconds / 2)
        self.update()

    # ── Dibujo ─────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._C_BG)
        self._draw_grid(p)
        self._draw_waveform(p)
        self._draw_blocks(p)
        self._draw_cursor(p)
        p.end()

    def _draw_grid(self, p: QPainter):
        h = self.height()
        p.setPen(QPen(self._C_GRID, 1))
        p.setFont(QFont("Sans", 7))
        first = int(self.start_pos)
        last = int(self.start_pos + self.visible_seconds) + 1
        for sec in range(first, last + 1):
            x = int(self.sec_to_x(sec))
            p.drawLine(x, 0, x, h)
            label = f"{sec // 60:02d}:{sec % 60:02d}"
            p.setPen(QPen(self._C_GRID.lighter(160), 1))
            p.drawText(x + 2, h - 4, label)
            p.setPen(QPen(self._C_GRID, 1))

    def _draw_waveform(self, p: QPainter):
        h = self.height()
        mid = h / 2
        amp = (h / 2) * 0.85
        peaks = self.audio.peaks
        n = len(peaks)
        pps = self.audio.peaks_per_second
        p.setPen(QPen(self._C_WAVE, 1))
        for x in range(self.width()):
            t = self.x_to_sec(x)
            idx = int(t * pps)
            if 0 <= idx < n:
                mn, mx = peaks[idx]
                y1 = mid - mx * amp
                y2 = mid - mn * amp
                p.drawLine(x, int(y1), x, int(y2))

    def _draw_blocks(self, p: QPainter):
        h = self.height()
        fm = QFontMetrics(QFont("Sans", 8))
        font = QFont("Sans", 8)
        for i, line in enumerate(self.lines):
            x0 = self.sec_to_x(line.start)
            end = self.lines[i + 1].start if i + 1 < len(self.lines) else self.audio.duration
            x1 = self.sec_to_x(end)
            if x1 < 0 or x0 > self.width():
                continue
            # Relleno del bloque
            fill = self._C_BLOCK_SEL if i == self.selected else self._C_BLOCK
            p.fillRect(int(x0), 0, max(1, int(x1 - x0)), h, fill)
            # Borde de inicio (lo que se arrastra)
            p.setPen(QPen(self._C_EDGE, 2))
            p.drawLine(int(x0), 0, int(x0), h)
            # Etiqueta: #índice tiempo + texto
            p.setPen(QPen(self._C_TEXT, 1))
            p.setFont(font)
            head = f"#{i + 1}  {line.start:.3f}"
            preview = strip_tags(line.text).replace('\n', ' ')
            avail = max(10, int(x1 - x0) - 8)
            elided = fm.elidedText(preview, Qt.TextElideMode.ElideRight, avail)
            p.drawText(int(x0) + 4, 14, elided)
            p.drawText(int(x0) + 4, h - 16, head)

    def _draw_cursor(self, p: QPainter):
        x = self.sec_to_x(self.playback_pos)
        if 0 <= x <= self.width():
            p.setPen(QPen(self._C_CURSOR, 1))
            p.drawLine(int(x), 0, int(x), self.height())

    # ── Hit-testing ────────────────────────────────────────────────────
    def _edge_at(self, x: float) -> int | None:
        for i, line in enumerate(self.lines):
            if abs(x - self.sec_to_x(line.start)) <= EDGE_GRAB_PX:
                return i
        return None

    def _block_at(self, x: float) -> int | None:
        for i, line in enumerate(self.lines):
            x0 = self.sec_to_x(line.start)
            end = self.lines[i + 1].start if i + 1 < len(self.lines) else self.audio.duration
            x1 = self.sec_to_x(end)
            if x0 <= x <= x1:
                return i
        return None

    # ── Interacción del mouse ──────────────────────────────────────────
    def mousePressEvent(self, event):
        x = event.position().x()
        edge = self._edge_at(x)
        if edge is not None:
            self._drag_index = edge
            self._drag_orig = self.lines[edge].start
            self._drag_start_x = x
            self._select(edge)
            return

        block = self._block_at(x)
        if block is not None:
            self._select(block)
        # Click en cualquier punto reposiciona el cursor de reproducción.
        self.seek_requested.emit(self.x_to_sec(x))

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._drag_index is None:
            # Cambia el cursor cerca de un borde arrastrable.
            near = self._edge_at(x) is not None
            self.setCursor(Qt.CursorShape.SizeHorCursor if near
                           else Qt.CursorShape.ArrowCursor)
            return

        i = self._drag_index
        new_start = self._drag_orig + (x - self._drag_start_x) / self.px_per_sec
        # Topes: no cruzar la línea anterior ni la siguiente.
        if i > 0:
            new_start = max(new_start, self.lines[i - 1].start + MIN_GAP)
        if i + 1 < len(self.lines):
            new_start = min(new_start, self.lines[i + 1].start - MIN_GAP)
        new_start = max(0.0, min(new_start, self.audio.duration))
        self.lines[i].start = new_start
        self.update()

    def mouseReleaseEvent(self, _event):
        if self._drag_index is not None:
            self.line_changed.emit(self._drag_index)
            self._drag_index = None

    def mouseDoubleClickEvent(self, event):
        block = self._block_at(event.position().x())
        if block is not None:
            self._select(block)
            self.edit_text_requested.emit(block)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            step = (delta / 120.0) * WHEEL_SCROLL_SECONDS
            self.set_start_pos(self.start_pos - step)

    def _select(self, index: int) -> None:
        self.selected = index
        self.line_selected.emit(index)
        self.update()


# ──────────────────────────────────────────────────────────────────────
# Diálogo principal del editor
# ──────────────────────────────────────────────────────────────────────
class LyricsSyncDialog(BaseDialog):
    """Ventana del editor de sincronización (mismo estilo que la app)."""

    def __init__(self, parent, vocals_path, lrc_path):
        self._vocals_path = vocals_path
        self._lrc_path = lrc_path
        self.saved = False

        super().__init__(parent, "Editor de sincronización", (1100, 560))

        # BaseDialog fija el tamaño; aquí lo liberamos para poder agrandar
        # manualmente con los SizeGrip (sin maximizar).
        self.setMinimumSize(760, 420)
        self.setMaximumSize(_QWIDGETSIZE_MAX, _QWIDGETSIZE_MAX)
        self.resize(1100, 560)

        self.audio = load_vocals(vocals_path)
        self.lines = parse_lrc(lrc_path)
        self.player = MiniVocalsPlayer(self.audio)
        # Estado inicial para detectar cambios sin guardar.
        self._original = self._snapshot()

        self._build_content()
        self._wire()
        self._create_grips()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    # Estilo opaco propio: sin esto el diálogo frameless se transparenta
    # y se funde con la ventana principal del fondo.
    _STYLE = """
        QDialog { background-color: #141420; border: 2px solid #7d73e8; }
        QPushButton {
            background-color: #2a2a3d; color: #e6e6f0;
            border: 1px solid #C04AD6; border-radius: 6px;
            padding: 5px 16px; font-weight: bold;
        }
        QPushButton:hover { background-color: #3a3a55; border: 1px solid #d96ce8; }
        QPushButton:pressed { background-color: #232336; }
        QScrollBar:horizontal { background: #1f1f2e; height: 14px; margin: 0; }
        QScrollBar::handle:horizontal {
            background: #7d73e8; border-radius: 6px; min-width: 30px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        QLabel { color: #cfcfe0; background: transparent; }
        QDoubleSpinBox {
            background: #2a2a3d; color: #e6e6f0;
            border: 1px solid #7d73e8; border-radius: 4px; padding: 2px;
        }
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
            background: #2a2a3d; border: none; width: 16px;
        }
        QDoubleSpinBox::up-arrow {
            width: 0; height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 6px solid #C04AD6;
        }
        QDoubleSpinBox::down-arrow {
            width: 0; height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid #C04AD6;
        }
        QDoubleSpinBox::up-arrow:hover { border-bottom-color: #d96ce8; }
        QDoubleSpinBox::down-arrow:hover { border-top-color: #d96ce8; }
        QCheckBox { color: #cfcfe0; background: transparent; }
    """

    # ── Construcción de UI ─────────────────────────────────────────────
    def _build_content(self):
        self.setStyleSheet(self._STYLE)

        self.waveform = WaveformWidget(self.audio, self.lines)
        self.main_layout.addWidget(self.waveform, stretch=1)

        # Nivel 1: scroll horizontal, pegado a la onda.
        scroll_row = QHBoxLayout()
        scroll_row.setContentsMargins(6, 2, 6, 2)
        self.scroll = QScrollBar(Qt.Orientation.Horizontal)
        scroll_row.addWidget(self.scroll)
        self.main_layout.addLayout(scroll_row)

        # Nivel 2: botones de opciones (separado del scroll).
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 0, 6, 0)
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(44, 28)
        bar.addWidget(self.play_btn)
        self.add_btn = QPushButton("＋ Línea")
        bar.addWidget(self.add_btn)
        self.del_btn = QPushButton("－ Línea")
        bar.addWidget(self.del_btn)

        # Offset global: desplaza TODAS las líneas el valor elegido.
        bar.addSpacing(12)
        bar.addWidget(QLabel("Offset:"))
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(0.1, 2.0)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setDecimals(1)
        self.offset_spin.setValue(0.5)
        self.offset_spin.setSuffix(" s")
        self.offset_spin.setFixedWidth(70)
        bar.addWidget(self.offset_spin)
        self.back_btn = QPushButton("« Antes")
        self.fwd_btn = QPushButton("Después »")
        bar.addWidget(self.back_btn)
        bar.addWidget(self.fwd_btn)
        # Si está marcado, el offset solo afecta líneas desde el cursor.
        self.from_cursor_chk = QCheckBox("Solo desde el cursor")
        # Indicador con los assets de checkbox de la app (incluyen la palomita);
        # el estilizado custom perdía la marca al activarse.
        unchecked = style_url('images/split_dialog/checkbox_unchecked.png')
        checked = style_url('images/split_dialog/checkbox_checked.png')
        hover = style_url('images/split_dialog/checkbox_hover01.png')
        self.from_cursor_chk.setStyleSheet(f"""
            QCheckBox {{ color: #cfcfe0; spacing: 8px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; image: url({unchecked}); }}
            QCheckBox::indicator:checked {{ image: url({checked}); }}
            QCheckBox::indicator:unchecked:hover {{ image: url({hover}); }}
        """)
        bar.addWidget(self.from_cursor_chk)
        bar.addStretch(1)
        self.main_layout.addLayout(bar)

        # Acciones guardar / cancelar
        actions = QHBoxLayout()
        actions.setContentsMargins(6, 4, 6, 6)
        self.hint = QLabel("Espacio: play/pausa · Supr: borrar línea · arrastra el borde de inicio · doble-click edita texto")
        self.hint.setStyleSheet("color:#9aa; background: transparent; border: none;")
        actions.addWidget(self.hint)
        actions.addStretch(1)
        self.save_btn = QPushButton("Guardar")
        self.cancel_btn = QPushButton("Cancelar")
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.save_btn)        
        self.main_layout.addLayout(actions)

        # Sin foco de teclado: así la barra espaciadora nunca activa un botón
        # por accidente y siempre llega al keyPressEvent del diálogo.
        for btn in (self.play_btn, self.add_btn, self.del_btn,
                    self.back_btn, self.fwd_btn, self.from_cursor_chk,
                    self.save_btn, self.cancel_btn):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._refresh_scroll_range()

    def _wire(self):
        self.play_btn.clicked.connect(self._toggle_play)
        self.add_btn.clicked.connect(self._add_line)
        self.del_btn.clicked.connect(self._delete_line)
        self.back_btn.clicked.connect(lambda: self._shift_all(-self.offset_spin.value()))
        self.fwd_btn.clicked.connect(lambda: self._shift_all(self.offset_spin.value()))
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn.clicked.connect(self.reject)
        self.scroll.valueChanged.connect(self._on_scroll)
        self.waveform.view_changed.connect(self._sync_scroll_from_view)
        self.waveform.seek_requested.connect(self._on_seek)
        self.waveform.edit_text_requested.connect(self._edit_text)

    # ── Scroll horizontal ──────────────────────────────────────────────
    def _refresh_scroll_range(self):
        # Trabaja en centisegundos para precisión entera.
        total = int(self.audio.duration * 100)
        page = int(self.waveform.visible_seconds * 100)
        self.scroll.setRange(0, max(0, total - page))
        self.scroll.setPageStep(max(1, page))
        self.scroll.setSingleStep(50)

    def _on_scroll(self, value: int):
        self.waveform.set_start_pos(value / 100.0, emit=False)

    def _sync_scroll_from_view(self):
        self.scroll.blockSignals(True)
        self.scroll.setValue(int(self.waveform.start_pos * 100))
        self.scroll.blockSignals(False)

    # ── Reproducción ───────────────────────────────────────────────────
    def _toggle_play(self):
        if self.player.playing:
            self.player.stop()
            self.play_btn.setText("▶")
        else:
            self.player.play(self.waveform.playback_pos)
            self.play_btn.setText("❚❚")

    def _on_seek(self, seconds: float):
        self.waveform.playback_pos = seconds
        if self.player.playing:
            self.player.play(seconds)
        self.waveform.update()

    def _tick(self):
        if self.player.playing:
            self.waveform.set_playback_pos(self.player.position)
            self._sync_scroll_from_view()
        elif self.play_btn.text() != "▶":
            # Terminó solo al llegar al final.
            self.play_btn.setText("▶")

    # ── Agregar línea ──────────────────────────────────────────────────
    def _add_line(self):
        """Crea una línea nueva en la posición actual del cursor."""
        pos = self.waveform.playback_pos
        text, ok = QInputDialog.getMultiLineText(
            self, "Nueva línea", f"Texto (inicio en {pos:.3f}s)", "",
        )
        if not ok:
            return
        # Se guardan las tags + el texto escrito por el usuario.
        new_line = LyricLine(pos, wrap_lyric(text))
        self.lines.append(new_line)
        self.lines.sort(key=lambda l: l.start)
        index = next(i for i, l in enumerate(self.lines) if l is new_line)
        self.waveform.selected = index
        self.waveform.line_selected.emit(index)
        self.waveform.update()

    def _delete_line(self):
        """Elimina la línea seleccionada."""
        i = self.waveform.selected
        if not (0 <= i < len(self.lines)):
            return
        del self.lines[i]
        self.waveform.selected = -1
        self.waveform.update()

    def _shift_all(self, delta: float):
        """Adelanta (+) o retrasa (−) líneas el offset elegido.

        Con "Solo desde el cursor" marcado, afecta únicamente las líneas
        cuyo inicio es >= la posición del cursor de reproducción.
        """
        dur = self.audio.duration
        threshold = (self.waveform.playback_pos
                     if self.from_cursor_chk.isChecked() else -1.0)
        for line in self.lines:
            if line.start >= threshold:
                line.start = max(0.0, min(dur, line.start + delta))
        self.waveform.update()

    # ── Teclado ────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._toggle_play()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self._delete_line()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Edición de texto ───────────────────────────────────────────────
    def _edit_text(self, index: int):
        if not (0 <= index < len(self.lines)):
            return
        was_playing = self.player.playing
        if was_playing:
            self.player.stop()
            self.play_btn.setText("▶")
        # Mostrar texto limpio (sin tags); reenvolver con tags al confirmar.
        clean = strip_tags(self.lines[index].text)
        text, ok = QInputDialog.getMultiLineText(
            self, "Editar texto", f"Línea #{index + 1}", clean,
        )
        if ok:
            self.lines[index].text = wrap_lyric(text)
            self.waveform.update()

    # ── Detección de cambios ───────────────────────────────────────────
    def _snapshot(self):
        return [(round(l.start, 3), l.text) for l in self.lines]

    def _has_changes(self) -> bool:
        return self._snapshot() != self._original

    # ── Guardar ────────────────────────────────────────────────────────
    def _save(self):
        if not self._has_changes():
            # Nada que guardar: cierra sin pedir nada.
            self.accept()
            return
        resp = styled_message_box(
            self, "Guardar", "¿Guardar los cambios en las letras?",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return  # seguir editando
        try:
            write_lrc(self._lrc_path, self.lines)
            self.saved = True
            self.accept()
        except Exception as e:
            styled_message_box(
                self, "Error", f"No se pudo guardar: {e}",
            )

    # ── Cierre ─────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._timer.stop()
        self.player.stop()
        super().closeEvent(event)

    def reject(self):
        if self._has_changes():
            resp = styled_message_box(
                self, "Cancelar", "Hay cambios sin guardar. ¿Descartarlos?",
                QMessageBox.Icon.Warning,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return  # seguir editando
        self._timer.stop()
        self.player.stop()
        super().reject()

    # ── Redimensionado (frameless) ─────────────────────────────────────
    def _create_grips(self):
        positions = ("top", "bottom", "left", "right",
                     "top_left", "top_right", "bottom_left", "bottom_right")
        self._grips = {pos: SizeGrip(self, pos) for pos in positions}
        self._position_grips()

    def _position_grips(self):
        w, h, s = self.width(), self.height(), 8
        coords = {
            "top": ((w - s) // 2, 0),
            "bottom": ((w - s) // 2, h - s),
            "left": (0, (h - s) // 2),
            "right": (w - s, (h - s) // 2),
            "top_left": (0, 0),
            "top_right": (w - s, 0),
            "bottom_left": (0, h - s),
            "bottom_right": (w - s, h - s),
        }
        for pos, grip in self._grips.items():
            grip.move(*coords[pos])
            grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'scroll'):
            self._refresh_scroll_range()
            self._sync_scroll_from_view()
        if hasattr(self, '_grips'):
            self._position_grips()
