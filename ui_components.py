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

import math
from PyQt6.QtCore import (Qt, QEvent, QPoint, QPointF, QRectF, QSize, QRect, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import (QPixmap, QPainter, QIcon, QColor, QFont, QPalette, QPen, QBrush,
                         QLinearGradient, QFontMetricsF)
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QPushButton, QDial,
                             QApplication, QStyle, QStyledItemDelegate,
                             QStyleOptionViewItem)
from resources import resource_path,bg_image
from chords import (DISPLAY_MIN_CHORD_S, chord_index_at, format_chord, format_key,
                    guitar_voicing, hide_short_chords)
from i18n import tr


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(35)
        self.bar_layout = QHBoxLayout(self)
        self.bar_layout.setContentsMargins(5, 0, 5, 0)

        # Título
        self.title = QLabel("Play It")
        self.title.setStyleSheet("color: white; font-weight: bold;background: transparent; border: none;")

        # Botones de control
        self.min_btn = QPushButton()
        self.min_btn.setIcon(QIcon(resource_path('images/main_window/min.png')))
        self.min_btn.setIconSize(QSize(16, 16))
        self.max_btn = QPushButton()
        self.max_btn.setIcon(QIcon(resource_path('images/main_window/max.png')))
        self.max_btn.setIconSize(QSize(16, 16))
        self.close_btn = QPushButton()
        self.close_btn.setIcon(QIcon(resource_path('images/main_window/cerrar.png')))
        self.close_btn.setIconSize(QSize(24, 24))

        # Estilos de botones
        estilacho = """
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px 0px;
                border-radius:12px
            }
            #close_btn:hover { background: #E81123; }
        """
        self.setStyleSheet(estilacho)
        self.close_btn.setObjectName("close_btn")

        # Sin foco por teclado: evita que Enter active minimizar/maximizar/cerrar
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Conexiones
        self.min_btn.clicked.connect(self.parent_window.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent_window.close)

        # Añadir elementos al layout
        self.bar_layout.addWidget(self.title)
        self.bar_layout.addStretch()
        self.bar_layout.addWidget(self.min_btn)
        self.bar_layout.addWidget(self.max_btn)
        self.bar_layout.addWidget(self.close_btn)

        # Variables para arrastrar ventana
        self.draggable = True
        self.drag_position = QPoint()

    def toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.max_btn.setIcon(QIcon(resource_path('images/main_window/max.png')))
            self.max_btn.setIconSize(QSize(16, 16))
        else:
            self.parent_window.showMaximized()
            self.max_btn.setIcon(QIcon(resource_path('images/main_window/rest.png')))
            self.max_btn.setIconSize(QSize(16, 16))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.draggable:
            self.drag_position = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.draggable:
            self.parent_window.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


class CustomDial(QDial):
    VALUE_COLOR = QColor("#F88FFF")  # rosa del tema (estilos.css)
    VALUE_TIMEOUT_MS = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.background = QPixmap(resource_path('images/main_window/dial_bg.png'))  # Imagen de fondo
        self.knob = QPixmap(resource_path('images/main_window/knob.png'))  # Imagen del knob

        # Indicador numérico temporal en el centro: visible mientras se
        # mueve el dial y 2 s después del último cambio. Solo con señales de
        # interacción del usuario (arrastre/rueda/teclado), no con el
        # setValue programático del arranque
        self._show_value = False
        self._value_timer = QTimer(self)
        self._value_timer.setSingleShot(True)
        self._value_timer.setInterval(self.VALUE_TIMEOUT_MS)
        self._value_timer.timeout.connect(self._hide_value)
        self.sliderMoved.connect(self._on_user_change)
        self.actionTriggered.connect(self._on_user_change)

    def _on_user_change(self, _value):
        self._show_value = True
        self._value_timer.start()  # reinicia: los 2 s cuentan desde el último movimiento
        self.update()

    def _hide_value(self):
        self._show_value = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Dibujar fondo escalado proporcionalmente
        bg_scaled = self.background.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(self.rect(), bg_scaled)

        # Calcular posición del knob
        angle = self._calculate_angle()
        pos = self._knob_position(angle)

        # Dibujar knob rotado y centrado
        knob_scaled = self.knob.scaled(
            20, 20,  # Tamaño deseado del knob
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.translate(pos)
        painter.rotate(angle + 135)  # Ajustar ángulo inicial
        painter.drawPixmap(-knob_scaled.width() // 2, -knob_scaled.height() // 2, knob_scaled)
        painter.resetTransform()

        if self._show_value:
            font = QFont(self.font())
            font.setBold(True)
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(self.VALUE_COLOR)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self.value()))

    def _calculate_angle(self):
        """Convierte el valor del dial a ángulo (0-270 grados)"""
        return 270 * (self.value() - self.minimum()) / (self.maximum() - self.minimum())

    def _knob_position(self, angle):
        """Calcula posición (x,y) basada en ángulo y radio"""
        radius = min(self.width(), self.height()) // 2 - 25  # Radio ajustable
        center = self.rect().center()
        theta = math.radians(angle + 135)  # Ajuste de coordenadas Qt

        return QPointF(
            center.x() + radius * math.cos(theta),
            center.y() + radius * math.sin(theta))

class PlaylistItemDelegate(QStyledItemDelegate):
    """Pinta la duración de la canción alineada a la derecha del renglón.

    El título se elide antes de invadir la zona de la duración; el color de
    la duración sigue al del ítem (blanco normal, negro cuando
    highlight_current_song pone ForegroundRole, color de selección si aplica).
    """

    DURATION_ROLE = Qt.ItemDataRole.UserRole + 1
    PATH_ROLE = Qt.ItemDataRole.UserRole + 2
    QUEUE_ROLE = Qt.ItemDataRole.UserRole + 3  # bool: la canción está en la cola de reproducción
    MARGIN = 6
    QUEUE_DOT_SIZE = 8
    QUEUE_DOT_COLOR = QColor("#B98CFF")

    def paint(self, painter, option, index):
        duration = index.data(self.DURATION_ROLE)
        queued = bool(index.data(self.QUEUE_ROLE))
        if not duration and not queued:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()

        dur_width = (opt.fontMetrics.horizontalAdvance(duration) + self.MARGIN
                     if duration else 0)
        dot_width = (self.QUEUE_DOT_SIZE + self.MARGIN) if queued else 0
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        # El renglón puede ser más ancho que el viewport (títulos largos):
        # anclar duración/indicador al borde visible, no al ancho total del ítem
        right_limit = text_rect.right()
        if opt.widget is not None:
            right_limit = min(right_limit,
                              opt.widget.viewport().rect().right() - self.MARGIN)
        reserved_width = dur_width + dot_width
        dur_rect = QRect(right_limit - dur_width, text_rect.top(),
                         dur_width, text_rect.height())
        # El punto de "en cola" va a la izquierda de la duración, ambos
        # anclados al mismo borde derecho.
        dot_rect = QRect(right_limit - reserved_width, text_rect.top(),
                         dot_width, text_rect.height())

        # Fondo/selección/icono + título elidido para no tapar duración/indicador
        opt.text = opt.fontMetrics.elidedText(
            opt.text, Qt.TextElideMode.ElideRight,
            right_limit - reserved_width - text_rect.left() - self.MARGIN)
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        painter.save()
        painter.setFont(opt.font)
        # Seleccionado primero: el fondo de selección (negro con el QSS de
        # foco) taparía el ForegroundRole oscuro del ítem en reproducción
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if opt.state & QStyle.StateFlag.State_Selected:
            pen_color = opt.palette.color(QPalette.ColorRole.HighlightedText)
        elif fg is not None:
            pen_color = fg.color()
        else:
            pen_color = opt.palette.color(QPalette.ColorRole.Text)
        painter.setPen(pen_color)
        if duration:
            painter.drawText(
                dur_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                duration)
        if queued:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.QUEUE_DOT_COLOR)
            radius = self.QUEUE_DOT_SIZE // 2
            center = QPoint(dot_rect.right() - radius, dot_rect.center().y())
            painter.drawEllipse(center, radius, radius)
        painter.restore()


class SizeGrip(QWidget):
    def __init__(self, parent, position):
        super().__init__(parent)
        self.parent_window = parent
        self.position = position
        self.setFixedSize(8, 8)
        self.setCursor(self.get_cursor())

    def get_cursor(self):
        return {
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
        }[self.position]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pos = event.globalPosition().toPoint()
            self.window_pos = self.parent_window.pos()
            self.window_size = self.parent_window.size()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.mouse_pos
            new_rect = QRect(self.window_pos, self.window_size)

            if self.position == "top":
                new_rect.adjust(0, delta.y(), 0, 0)
            elif self.position == "bottom":
                new_rect.adjust(0, 0, 0, delta.y())
            elif self.position == "left":
                new_rect.adjust(delta.x(), 0, 0, 0)
            elif self.position == "right":
                new_rect.adjust(0, 0, delta.x(), 0)
            elif self.position == "top_left":
                new_rect.adjust(delta.x(), delta.y(), 0, 0)
            elif self.position == "top_right":
                new_rect.adjust(0, delta.y(), delta.x(), 0)
            elif self.position == "bottom_left":
                new_rect.adjust(delta.x(), 0, 0, delta.y())
            elif self.position == "bottom_right":
                new_rect.adjust(0, 0, delta.x(), delta.y())

            self.parent_window.setGeometry(new_rect.normalized())
            event.accept()


class DialogTitleBar(TitleBar):
    def __init__(self, parent):
        super().__init__(parent)

        # Eliminar botones que no necesitamos
        self.min_btn.setVisible(False)
        self.max_btn.setVisible(False)

        btn_style = """
                            DialogTitleBar {
                                background: transparent;
                            }
                            QPushButton {
                                background: transparent;
                                border: 0px;
                                padding: 0px 0px;
                                border-radius:12px
                            }
                            #close_btn:hover { background: #E81123; }
                        """
        self.setStyleSheet(btn_style)

        # Cerrar = reject. Quitar antes la conexión a close() heredada de
        # TitleBar: con ambas, un clic disparaba reject dos veces (close()
        # también llama reject vía closeEvent) y los diálogos con
        # confirmación de cambios preguntaban dos veces.
        self.close_btn.clicked.disconnect()
        self.close_btn.clicked.connect(parent.reject)


class StyledButtons(QWidget):
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._create_buttons()

    def _create_buttons(self):
        # botón ACEPTAR
        self.yes_btn = QPushButton()
        self.yes_btn.setObjectName("aceptar_btn")
        self.yes_btn.setFixedSize(70, 70)
        self._yes_normal = "images/split_dialog/aceptar_btn.png"
        self._yes_disabled = "images/split_dialog/aceptar_btn_disabled.png"
        bg_image(self.yes_btn, self._yes_normal)
        self.yes_btn.clicked.connect(self.accepted)

        # botón CANCELAR
        self.no_btn = QPushButton()
        self.no_btn.setObjectName("cancelar_btn")
        self.no_btn.setFixedSize(70, 70)
        self._no_normal = "images/split_dialog/cancelar_btn.png"
        self._no_disabled = "images/split_dialog/cancelar_btn_disabled.png"
        bg_image(self.no_btn, self._no_normal)
        self.no_btn.clicked.connect(self.rejected)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.yes_btn)
        layout.addWidget(self.no_btn)

    def setEnabled(self, on: bool):
        self.yes_btn.setEnabled(on)
        bg_image(self.yes_btn, self._yes_normal if on else self._yes_disabled)


class ChordCarouselWidget(QWidget):
    """Carrusel de acordes del panel de letras: tonalidad arriba, diagrama de
    guitarra del acorde actual a la izquierda, tarjetas anterior / actual /
    siguiente y debajo una barra que se llena hasta el próximo cambio.

    Vive arriba del layout de `lyrics_container`, donde antes iba el
    encabezado artista/título, así que viaja solo al fullscreen. Su tamaño sigue al del padre (`reposition`, vía
    eventFilter): alto proporcional con mínimo legible, ancho tope 5:1.
    Transparente al mouse para no robar el doble clic que entra/sale del
    fullscreen. Pinta todo en `paintEvent` con colores propios: el QSS que se
    re-aplica en fullscreen no le afecta.

    Solo pinta: la posición la empuja `AudioPlayer` con `set_time`.
    """

    MARGIN = 14
    MIN_H = 84
    MAX_H = 130

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._starts: list[float] = []
        self._labels: list[str] = []
        self._raw: list = []  # tal como viene de chords.json, sin filtrar
        self._min_s = DISPLAY_MIN_CHORD_S
        self._duration = 0.0
        self._key = ("", "major")
        self._notation = "american"
        self._idx = -1
        self._t = 0.0
        self._watched = None
        self._watch(parent)
        self.hide()

    # ── API ──────────────────────────────────────────────────────────────
    def set_chords(self, data: dict):
        self._duration = float((data or {}).get("duration") or 0.0)
        self._raw = (data or {}).get("chords") or []
        self._key = ((data or {}).get("key") or "", (data or {}).get("mode") or "major")
        self._t = 0.0
        self._apply_filter()

    def set_min_duration(self, min_s: float):
        """Oculta los cambios más cortos que `min_s` (0 = mostrar todos)."""
        self._min_s = min_s
        self._apply_filter()

    def _apply_filter(self):
        chords = hide_short_chords(self._raw, self._duration, self._min_s)
        self._starts = [c[0] for c in chords]
        self._labels = [c[1] for c in chords]
        self._idx = chord_index_at(self._starts, self._t)
        self.update()

    def has_chords(self) -> bool:
        return bool(self._starts)

    def set_notation(self, notation: str):
        self._notation = notation
        self.update()

    def set_time(self, t: float):
        # Cambio instantáneo: un deslizamiento (antes 160 ms) hacía que el
        # acorde nuevo llegara al centro después de oírse.
        self._idx = chord_index_at(self._starts, t)
        self._t = t
        self.update()

    def seconds_to_next(self, t: float) -> float | None:
        """Segundos desde `t` hasta el próximo cambio; `None` si no hay."""
        i = chord_index_at(self._starts, t) + 1
        return self._starts[i] - t if i < len(self._starts) else None

    def labels_at_current(self) -> tuple[str, str, str]:
        """(anterior, actual, siguiente) como se muestran; "" si no hay."""
        def lab(i):
            if 0 <= i < len(self._labels):
                return format_chord(self._labels[i], self._notation)
            return ""
        return lab(self._idx - 1), lab(self._idx), lab(self._idx + 1)

    def current_label(self) -> str:
        """Etiqueta cruda (americana) del acorde actual: la usa el diagrama."""
        return self._labels[self._idx] if 0 <= self._idx < len(self._labels) else ""

    def progress(self) -> float:
        """Fracción transcurrida del acorde actual (0..1)."""
        i = self._idx
        if not (0 <= i < len(self._starts)):
            return 0.0
        end = self._starts[i + 1] if i + 1 < len(self._starts) else self._duration
        span = end - self._starts[i]
        return min(1.0, max(0.0, (self._t - self._starts[i]) / span)) if span > 0 else 0.0

    # ── Geometría ────────────────────────────────────────────────────────
    def _watch(self, parent):
        if self._watched is not None:
            self._watched.removeEventFilter(self)
        self._watched = parent
        if parent is not None:
            parent.installEventFilter(self)
            self.reposition()

    def eventFilter(self, obj, event):
        if obj is self._watched and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.reposition()
        return False

    def reposition(self):
        """Ajusta el tamaño al del padre; la posición la pone el layout."""
        parent = self.parentWidget()
        if parent is None:
            return
        h = int(min(self.MAX_H, max(self.MIN_H, parent.height() * 0.11)))
        w = min(parent.width() - 2 * self.MARGIN, h * 5)
        self.setFixedSize(max(0, w), h)

    # ── Pintado ──────────────────────────────────────────────────────────
    def _font(self, px: float, bold: bool = True) -> QFont:
        f = QFont(self.font())
        f.setBold(bold)
        f.setPixelSize(max(8, int(px)))
        return f

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        u = h / 112  # medidas de diseño pensadas para 112 px de alto

        bg = QLinearGradient(0, 0, w, 0)
        bg.setColorAt(0, QColor("#081e33"))
        bg.setColorAt(0.5, QColor("#16172e"))
        bg.setColorAt(1, QColor("#2b1039"))
        p.setPen(QPen(QColor(96, 143, 194, 125), 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 14 * u, 14 * u)

        pad = 10 * u
        key_h = 18 * u
        key_text = format_key(*self._key, self._notation)
        if key_text:
            p.setFont(self._font(12 * u))
            p.setPen(QColor("#a1b5d8"))
            p.drawText(QRectF(pad + 3 * u, 6 * u, w - 2 * pad, key_h),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"♪  {tr('Tonalidad')}: {key_text}")

        top = 6 * u + key_h + 4 * u
        diag = QRectF(pad, top, 68 * u, h - pad - top)
        self._draw_diagram(p, diag, u)

        # Tarjetas + barra de progreso del acorde, a la derecha del diagrama
        bar_h = max(3.0, 4 * u)
        cards = QRectF(diag.right() + 8 * u, top,
                       w - pad - diag.right() - 8 * u, h - pad - top - bar_h - 6 * u)
        gap = 7 * u
        cell = (cards.width() - 2 * gap) / 3
        for i in range(3):
            rect = QRectF(cards.left() + i * (cell + gap), cards.top(), cell, cards.height())
            if i == 1:
                fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
                fill.setColorAt(0, QColor("#8d279d"))
                fill.setColorAt(1, QColor("#392457"))
                p.setBrush(QBrush(fill))
                p.setPen(QPen(QColor("#df65ef"), max(1.5, 2 * u)))
            else:
                p.setBrush(QColor(33, 34, 65, 215))
                p.setPen(QPen(QColor(114, 95, 166, 135), 1))
            p.drawRoundedRect(rect, 11 * u, 11 * u)

        prev, cur, nxt = self.labels_at_current()
        for text, slot, px, color in (
            (prev, 0, 21 * u, QColor("#b6a2d2")),
            (cur, 1, 30 * u, QColor("#ffffff")),
            (nxt, 2, 21 * u, QColor("#b6a2d2")),
        ):
            if not text:
                continue
            font = self._font(px)
            text_w = QFontMetricsF(font).horizontalAdvance(text)
            if text_w > cell * 0.88:  # "C#dim" en panel angosto: encoger
                font = self._font(px * cell * 0.88 / text_w)
            p.setFont(font)
            p.setPen(color)
            rect = QRectF(cards.left() + slot * (cell + gap), cards.top(),
                          cell, cards.height())
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        bar = QRectF(cards.left(), h - pad - bar_h, cards.width(), bar_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
        frac = self.progress()
        if frac > 0:
            p.setBrush(QColor("#d75ce9"))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar_h),
                              bar_h / 2, bar_h / 2)
        p.end()

    def _draw_diagram(self, p: QPainter, area: QRectF, u: float):
        """Diagrama de guitarra del acorde actual: 6 cuerdas, ventana de 4
        trastes, × / ○ sobre la cejuela y barra cuando es cejilla."""
        p.save()
        p.setPen(QPen(QColor(118, 110, 182, 135), 1))
        p.setBrush(QColor(35, 37, 72, 200))
        p.drawRoundedRect(area, 10 * u, 10 * u)
        frets = guitar_voicing(self.current_label())
        if frets is None:  # "N" o sin acorde: caja vacía
            p.restore()
            return

        x0, x1 = area.left() + 14 * u, area.right() - 8 * u
        xstep = (x1 - x0) / 5
        y0 = area.top() + 16 * u
        fstep = (area.bottom() - 6 * u - y0) / 4
        pressed = [f for f in frets if f > 0]
        start = 1 if max(pressed, default=0) <= 4 else min(pressed)

        p.setPen(QPen(QColor("#99a8c7"), 1))
        for i in range(6):
            x = x0 + i * xstep
            p.drawLine(QPointF(x, y0), QPointF(x, y0 + 4 * fstep))
        for i in range(5):
            y = y0 + i * fstep
            nut = i == 0 and start == 1
            p.setPen(QPen(QColor("#d0c8ef"), max(2.0, 3 * u) if nut else 1))
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
        if start > 1:
            p.setFont(self._font(9 * u, bold=False))
            p.setPen(QColor("#c7b1ea"))
            p.drawText(QRectF(area.left(), y0, x0 - area.left() - 2 * u, fstep),
                       Qt.AlignmentFlag.AlignCenter, str(start))

        dot = min(xstep, fstep) * 0.36
        played = [i for i, f in enumerate(frets) if f >= 0]
        first = played[0] if played else 5
        # Cejilla: la primera cuerda tocada y la 1ª aguda en el mismo traste,
        # sin cuerdas al aire (G abierto empieza y acaba en 3 pero no lo es).
        barre = frets[first] if (frets[first] > 0 and frets[first] == frets[5]
                                 and 0 not in frets) else 0
        p.setBrush(QColor("#df61ef"))
        p.setPen(Qt.PenStyle.NoPen)
        if barre:
            y = y0 + (barre - start + 0.5) * fstep
            p.drawRoundedRect(QRectF(x0 + first * xstep - dot, y - dot,
                                     (5 - first) * xstep + 2 * dot, 2 * dot), dot, dot)
        mark_y = y0 - 8 * u
        for i, f in enumerate(frets):
            x = x0 + i * xstep
            if f == -1:
                p.setPen(QColor("#9ba7bf"))
                p.setFont(self._font(10 * u, bold=False))
                p.drawText(QRectF(x - 6 * u, mark_y - 6 * u, 12 * u, 12 * u),
                           Qt.AlignmentFlag.AlignCenter, "×")
            elif f == 0:
                p.setPen(QPen(QColor("#d6b8f4"), 1.3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x, mark_y), 3.2 * u, 3.2 * u)
            elif f != barre:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#df61ef"))
                p.drawEllipse(QPointF(x, y0 + (f - start + 0.5) * fstep), dot, dot)
        p.restore()
