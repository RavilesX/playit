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

"""Visualizador de audio estilo CAVA para PlayIt.

Replica el algoritmo de CAVA (cavacore) en NumPy en vez de depender del binario:
toma el PCM que la app ya mezcla en ``AudioPlayer._stream_writer``, calcula una FFT,
mapea las magnitudes a barras con espaciado logarítmico y aplica suavizado
(auto-sensibilidad + gravedad). Multiplataforma (Windows/Linux) y sin dependencias
nuevas: solo NumPy y PyQt6, que el proyecto ya usa.

Dos piezas:

- ``AudioAnalyzer``  (QObject): hace el DSP. ``process()`` se llama desde el hilo de
  audio; emite ``bars_ready`` (Qt encola la señal hacia el hilo GUI de forma segura).
- ``VisualizerWidget`` (QWidget): pinta las barras. Va detrás de los controles, con
  fondo transparente y sin robar clics del ratón.
"""

import time

import numpy as np
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush
from PyQt6.QtWidgets import QWidget


class AudioAnalyzer(QObject):
    """Convierte chunks de PCM en alturas de barras (0.0–1.0).

    El cálculo es barato (FFT de ``fft_size`` muestras, ~decenas de µs) y se limita a
    ``framerate`` fps para no recargar el hilo de audio ni el repintado.
    """

    bars_ready = pyqtSignal(object)  # np.ndarray float32 (num_bars,) en [0, 1]

    def __init__(self, num_bars: int = 48, fft_size: int = 2048,
                 sample_rate: int = 44100, framerate: int = 30,
                 low_freq: float = 50.0, high_freq: float = 12000.0,
                 parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.fft_size = fft_size
        self.low_freq = low_freq
        self.high_freq = high_freq
        self.enabled = True

        self.gravity = 0.92        # decaimiento por frame cuando la barra baja
        self._peak_decay = 0.999   # caída lenta de la auto-sensibilidad
        self._interval = 1.0 / max(1, framerate)

        self._window = np.hanning(fft_size).astype(np.float32)
        self._buf = np.zeros(fft_size, dtype=np.float32)
        self._prev = np.zeros(num_bars, dtype=np.float32)
        self._peak = 1e-6
        self._last_emit = 0.0

        self.configure(sample_rate)

    def configure(self, sample_rate: int):
        """Recalcula los rangos de bins por barra (espaciado logarítmico)."""
        nyquist = sample_rate / 2.0
        half = self.fft_size // 2
        edges = np.logspace(
            np.log10(self.low_freq),
            np.log10(min(self.high_freq, nyquist - 1)),
            self.num_bars + 1,
        )
        idx = (edges / nyquist * half).astype(int)
        idx = np.clip(idx, 1, half)
        # Garantiza al menos un bin por barra y monotonía creciente.
        for i in range(1, len(idx)):
            if idx[i] <= idx[i - 1]:
                idx[i] = idx[i - 1] + 1
        idx = np.clip(idx, 1, half)
        self._bin_idx = idx

    def reset(self):
        """Limpia el estado de suavizado (al iniciar canción o tras un seek)."""
        self._buf[:] = 0.0
        self._prev[:] = 0.0
        self._peak = 1e-6
        self._last_emit = 0.0

    def process(self, chunk: np.ndarray):
        """Recibe un chunk (frames, canales) o mono desde el hilo de audio."""
        if not self.enabled:
            return

        mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
        self._append(mono.astype(np.float32, copy=False))

        now = time.monotonic()
        if now - self._last_emit < self._interval:
            return
        self._last_emit = now

        bars = self._compute()
        self.bars_ready.emit(bars)

    def _append(self, mono: np.ndarray):
        n = len(mono)
        if n >= self.fft_size:
            self._buf[:] = mono[-self.fft_size:]
        else:
            self._buf[:-n] = self._buf[n:]
            self._buf[-n:] = mono

    def _compute(self) -> np.ndarray:
        spec = np.abs(np.fft.rfft(self._buf * self._window))

        idx = self._bin_idx
        out = np.empty(self.num_bars, dtype=np.float32)
        for i in range(self.num_bars):
            lo, hi = idx[i], idx[i + 1]
            out[i] = spec[lo:hi].mean() if hi > lo else spec[lo]

        # Compresión de potencia: realza señales débiles (similar al look de CAVA).
        out = np.sqrt(out)

        # Auto-sensibilidad: normaliza al pico reciente para llenar la altura.
        cur = float(out.max())
        self._peak = max(self._peak * self._peak_decay, cur, 1e-6)
        norm = np.clip(out / self._peak, 0.0, 1.0)

        # Subida instantánea, caída por gravedad (suavizado de CAVA).
        fall = self._prev * self.gravity
        self._prev = np.where(norm > self._prev, norm, fall).astype(np.float32)
        return self._prev.copy()


class VisualizerWidget(QWidget):
    """Pinta las barras detrás de los controles. Transparente a fondo y a clics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._bars = np.zeros(0, dtype=np.float32)
        self._gradient = None
        self._gradient_h = -1

    def set_bars(self, bars: np.ndarray):
        self._bars = bars
        self.update()

    def clear(self):
        if self._bars.size:
            self._bars = np.zeros_like(self._bars)
            self.update()

    def _build_gradient(self, h: int):
        grad = QLinearGradient(0, h, 0, 0)        # abajo -> arriba
        #grad.setColorAt(0.0, QColor(255, 90, 200, 200))   # rosa (base)
        grad.setColorAt(0.0, QColor(255, 255, 255, 100))   # rosa (base)
        grad.setColorAt(0.55, QColor(200, 70, 230, 180))  # violeta
        grad.setColorAt(1.0, QColor(80, 150, 255, 150))   # azul (cima)
        self._gradient = QBrush(grad)
        self._gradient_h = h

    def paintEvent(self, event):
        n = self._bars.size
        if n == 0:
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        if self._gradient is None or self._gradient_h != h:
            self._build_gradient(h)
        brush = self._gradient
        assert brush is not None

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(brush)

        slot = w / n
        gap = max(1.0, slot * 0.25)
        bar_w = slot - gap
        radius = bar_w * 0.4

        for i in range(n):
            bh = float(self._bars[i]) * h
            if bh < 1.0:
                continue
            x = i * slot + gap / 2.0
            rect = QRectF(x, h - bh, bar_w, bh)
            painter.drawRoundedRect(rect, radius, radius)
