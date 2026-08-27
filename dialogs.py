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

from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint, QDir
from PyQt6.QtGui import QDesktopServices, QImage, QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton, QLineEdit, QHBoxLayout,
    QFileDialog, QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QMenu, QWidget, QCompleter,
)
from demucs_worker import AUDIO_INPUT_FILTER
from resources import resource_path, bg_image, styled_message_box, style_url
from ui_components import DialogTitleBar, StyledButtons
from version import __version__
import html
import logging
import os
import string
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseDialog(QDialog):
    def __init__(self, parent=None, title: str = "", size: tuple[int, int] = (400, 300)):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setFixedSize(*size)
        self._setup_ui()
        self._center()

    def _setup_ui(self):
        self._create_title_bar()
        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.title_bar)
        self.setLayout(self.main_layout)

    def _create_title_bar(self):
        self.title_bar = DialogTitleBar(self)
        self.title_bar.title.setText(self.windowTitle())

    def _center(self):
        if not self.parent_window:
            return

        parent_geo = self.parent_window.geometry()
        x = (parent_geo.width() - self.width()) // 2
        y = (parent_geo.height() - self.height()) // 2
        self.move(QPoint(x, y))


class AboutDialog(BaseDialog):
    PAYPAL_URL = "https://www.paypal.com/donate/?business=TULUZ868SK2BG&no_recurring=0&item_name=Desarrollo+apps+sin+fines+de+lucro%2C+no+necesitas+donar+para+usarlas%2C+pero+me+ayuda+y+me+inspira+a+seguir+creando+soluciones.&currency_code=USD"

    def __init__(self, parent=None):
        super().__init__(parent, "Sobre Playit", (450, 550))
        self._setup_content()

    def _setup_content(self):
        text_edit = self._create_text_display()

        paypal_btn = self._create_paypal_button()

        # Layout
        self.main_layout.addWidget(text_edit)
        self.main_layout.addWidget(
            QLabel("Se aceptan donaciones"),
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.main_layout.addWidget(paypal_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _create_text_display(self) -> QTextEdit:
        version_path = resource_path('images/main_window/main_icon.png')
        about_text = self._get_about_text(version_path)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(about_text)
        text_edit.setStyleSheet("""
            QTextEdit {
                color: #fc5490;
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0,0,0,0.7), stop:1 rgba(0,0,0,0.1)
                );
                border: 0px;
                padding-top: 2px;
                font-size: 16px;
            }
        """)
        return text_edit

    def _create_paypal_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(70, 70)
        btn.setObjectName("aceptar_btn")
        bg_image(btn, "images/main_window/paypal.png")
        btn.clicked.connect(self._open_paypal_donation)
        return btn

    def _open_paypal_donation(self):
        url = QUrl(self.PAYPAL_URL)
        if url.isValid():
            QDesktopServices.openUrl(url)
        else:
            logger.warning("Invalid PayPal URL!")

    def _get_about_text(self, version_path: str) -> str:
        return f"""
        <style>
        li{{color:#b23c56;}}
        sub{{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}}
        </style>
        <center><img src="{version_path}" width="100" height="100"></center>
        <center><sub>Versión {__version__}</sub></center>
        <p>Reproductor de Audio con separación de pistas.</p>
        <sub>ESTE SOFTWARE SE PROPORCIONA 'TAL CUAL', SIN GARANTÍAS DE NINGÚN TIPO, YA SEAN EXPRESAS O IMPLÍCITAS, INCLUYENDO, PERO NO LIMITADO A, GARANTÍAS DE COMERCIABILIDAD, IDONEIDAD PARA UN PROPÓSITO PARTICULAR Y NO INFRACCIÓN. EN NINGÚN CASO, LOS AUTORES O COLABORADORES SERÁN RESPONSABLES DE DAÑOS DIRECTOS, INDIRECTOS, INCIDENTALES, ESPECIALES, EJEMPLARES O CONSECUENTES (INCLUYENDO, PERO NO LIMITADO A, LA ADQUISICIÓN DE BIENES O SERVICIOS SUSTITUTOS; LA PÉRDIDA DE USO, DATOS O BENEFICIOS; O LA INTERRUPCIÓN DEL NEGOCIO) DE CUALQUIER MANERA CAUSADOS Y BAJO CUALQUIER TEORÍA DE RESPONSABILIDAD, YA SEA POR CONTRATO, RESPONSABILIDAD ESTRICTA O AGRAVIO (INCLUYENDO NEGLIGENCIA O DE OTRA MANERA) QUE SURJA DE CUALQUIER FORMA DEL USO DE ESTE SOFTWARE, INCLUSO SI SE HA AVISADO DE LA POSIBILIDAD DE TALES DAÑOS. Mire la Licencia pública general GNU para obtener más detalles.Debería haber recibido una copia de la Licencia Pública General GNU junto con este programa. En caso contrario, consulte: https://www.gnu.org/licenses/.</sub>
        <p>Desarrollado por: RavilesX</p><p>Email: ravilesx@gmail.com</p>
        """


class SearchDialog(BaseDialog):
    search_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, "Buscar en Playlist", (300, 150))
        self._setup_search_ui()

    def _setup_search_ui(self):
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Introduce texto a buscar...")
        # Enter siempre dispara la búsqueda, sin depender del botón default
        self.search_text.returnPressed.connect(self._accept_search)

        # Buttons
        btn_layout = self._create_button_layout()

        # Layout
        self.main_layout.addWidget(self.search_text)
        self.main_layout.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self.search_text.setFocus()
        self.search_text.selectAll()

    def _create_button_layout(self) -> QHBoxLayout:
        btn_layout = QHBoxLayout()

        self.accept_btn = self._create_action_button(
            "aceptar_btn", "images/split_dialog/aceptar_btn.png",
            self._accept_search
        )
        # Sin default/autoDefault: evita que Enter dispare doble
        # (returnPressed + click del botón default) o caiga en cancelar
        self.accept_btn.setDefault(False)
        self.accept_btn.setAutoDefault(False)

        self.cancel_btn = self._create_action_button(
            "cancelar_btn", "images/split_dialog/cancelar_btn.png",
            self.reject
        )
        self.cancel_btn.setAutoDefault(False)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.accept_btn)
        return btn_layout

    def _create_action_button(self, obj_name: str, image_path: str, callback) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(obj_name)
        btn.setFixedSize(70, 70)
        bg_image(btn, image_path)
        btn.clicked.connect(callback)
        return btn

    def _accept_search(self):
        # No cierra el diálogo: cada Enter avanza a la siguiente coincidencia
        text = self.search_text.text().strip()
        if text:
            self.search_requested.emit(text)

class UpdateDialog(BaseDialog):
    def __init__(self, parent=None, message: str = "", show_cancel: bool = False):
        super().__init__(parent, "Buscar actualizaciones", (320, 180))
        self._setup_update_ui(message, show_cancel)

    def _setup_update_ui(self, message: str, show_cancel: bool):
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet("color: white; font-weight: bold;")

        btn_layout = QHBoxLayout()

        self.accept_btn = self._create_action_button(
            "aceptar_btn", "images/split_dialog/aceptar_btn.png", self.accept
        )
        self.accept_btn.setAutoDefault(False)

        if show_cancel:
            self.cancel_btn = self._create_action_button(
                "cancelar_btn", "images/split_dialog/cancelar_btn.png", self.reject
            )
            self.cancel_btn.setAutoDefault(False)
            btn_layout.addWidget(self.cancel_btn)

        btn_layout.addWidget(self.accept_btn)

        self.main_layout.addWidget(self.message_label)
        self.main_layout.addLayout(btn_layout)

    def _create_action_button(self, obj_name: str, image_path: str, callback) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(obj_name)
        btn.setFixedSize(70, 70)
        bg_image(btn, image_path)
        btn.clicked.connect(callback)
        return btn


class QueueDialog(BaseDialog):
    def __init__(self, audio_player, parent=None):
        super().__init__(parent, "Canciones en Cola", (400, 550))
        self._setup_queue_display(audio_player)

    def _setup_queue_display(self, audio_player):
        queue_html = self._generate_queue_html(audio_player.demucs_queue)

        queue_edit = QTextEdit()
        queue_edit.setReadOnly(True)
        queue_edit.setHtml(queue_html)
        queue_edit.setObjectName("queue_text")
        queue_edit.setStyleSheet("""
            #queue_text {
                color: #7E54AF;
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(0,0,0,0.5), stop:1 rgba(0,0,0,0.1)
                );
                border: 0px;
                padding-top: 2px;
                font-size: 16px;
            }
        """)

        self.main_layout.addWidget(queue_edit)

    def _generate_queue_html(self, queue: list) -> str:
        html = """
        <H1 style='color: #3AABEF;'><center>Artista - Canción</center></H1>
        <style>
        li{color:#b23c56;}
        sub{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}
        </style><ul>
        """

        for item in queue:
            html += f"<li><center>{item['artist']} - {item['song']}</center></li>\n"

        html += "</ul>"
        return html


# Columnas y rol de datos de la tabla de PlaybackQueueDialog, a nivel de
# módulo para que _QueueTable pueda usarlos sin acoplarse a esa clase (que
# se define más abajo en este archivo). PlaybackQueueDialog los expone
# también como atributos de clase (mismos valores) por compatibilidad.
_QUEUE_SONG_ROLE = Qt.ItemDataRole.UserRole
_QUEUE_COL_SONG, _QUEUE_COL_DURATION, _QUEUE_COL_TAGS = range(3)


class _QueueTable(QTableWidget):
    """Grid de la cola: Supr quita la fila seleccionada; arrastrar una fila
    la reordena.

    Reordenamiento 100% manual (mousePress/Move/Release), sin el Drag & Drop
    nativo de Qt (QDrag/dropEvent): QAbstractItemView, del lado donde arranca
    el arrastre, hace su propia limpieza posterior al soltar cuando la
    acción resuelta es Move — asume que dropMimeData() ya movió los datos y
    borra la fila de origen por su cuenta. Como _move_row ya reubica la fila
    a mano, esa limpieza automática de Qt caía sobre el índice viejo (ya
    movido) y terminaba borrando la fila. Desactivar el DnD nativo por
    completo es la única forma de que ese ciclo de limpieza no se dispare.
    """

    DRAG_THRESHOLD = 4  # px; evita que un clic con la mano temblando cuente como arrastre

    INDICATOR_COLOR = QColor("#B98CFF")

    def __init__(self, on_change, parent=None):
        super().__init__(0, 3, parent)
        self._on_change = on_change
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._press_row = -1
        self._press_pos = None
        self._dragging = False
        self._indicator_y = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.currentRow() != -1:
            self.removeRow(self.currentRow())
            self._on_change()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_row = self.rowAt(event.position().toPoint().y())
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_row == -1 or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        pos = event.position().toPoint()
        if not self._dragging:
            if (pos - self._press_pos).manhattanLength() < self.DRAG_THRESHOLD:
                return
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        # No se delega a super(): el comportamiento por defecto arrastraría
        # la selección detrás del cursor en vez de mantener resaltada la
        # fila que se está moviendo.
        self._set_indicator_y(self._raw_drop_row(pos))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self.unsetCursor()
            self._set_indicator_y(None)
            src_row = self._press_row
            raw_target = self._raw_drop_row(event.position().toPoint())
            # raw_target es "insertar antes de esta fila" en la indexación
            # ACTUAL (previa a mover nada); si cae después del origen, hay
            # que restarle 1 porque quitar la fila de origen recorre todo
            # lo que está detrás un lugar.
            target_row = raw_target - 1 if raw_target > src_row else raw_target
            if 0 <= target_row < self.rowCount() and target_row != src_row:
                self._move_row(src_row, target_row)
                self._on_change()
            self._press_row = -1
            self._dragging = False
            return
        self._press_row = -1
        self._dragging = False
        super().mouseReleaseEvent(event)

    def _raw_drop_row(self, pos: QPoint) -> int:
        """Fila (0..rowCount, ambos inclusive) antes de la cual caería el
        drop en la posición actual del mouse, en la indexación sin mover
        nada todavía. rowCount() significa "después de la última fila"."""
        row = self.rowAt(pos.y())
        if row == -1:
            return self.rowCount()
        rect = self.visualRect(self.model().index(row, 0))
        return row + 1 if pos.y() > rect.center().y() else row

    def _set_indicator_y(self, raw_target: int | None):
        """Guarda la coordenada Y de la línea de destino (o None para
        ocultarla) y repinta solo si cambió, para no repintar en cada pixel
        de movimiento del mouse."""
        y = None
        if raw_target is not None:
            if raw_target >= self.rowCount():
                if self.rowCount() == 0:
                    y = 0
                else:
                    y = self.visualRect(self.model().index(self.rowCount() - 1, 0)).bottom()
            else:
                y = self.visualRect(self.model().index(raw_target, 0)).top()
        if y != self._indicator_y:
            self._indicator_y = y
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._indicator_y is None:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QPen(self.INDICATOR_COLOR, 2))
        painter.drawLine(0, self._indicator_y, self.viewport().width(), self._indicator_y)
        painter.end()

    def _move_row(self, src: int, dst: int):
        # Columnas con QTableWidgetItem (Canción, Duración): take/setItem es
        # la forma soportada por Qt de transplantarlas, sin riesgo.
        row_items = {
            c: self.takeItem(src, c)
            for c in range(self.columnCount()) if c != _QUEUE_COL_TAGS
        }
        # La celda de Tags usa cellWidget (_TagsCell), no QTableWidgetItem:
        # NO se debe reutilizar ese widget "movido a mano". QAbstractItemView
        # guarda internamente su propio mapa índice→widget aparte del árbol
        # padre/hijo normal; con setParent(None) + removeRow() ese mapa
        # interno igual intenta destruir el widget mientras Python todavía
        # lo referencia para reinsertarlo — use-after-free, y de ahí el
        # segfault. Más simple y seguro: guardar solo el song dict y
        # reconstruir un _TagsCell nuevo en el destino (misma operación que
        # ya hace _reload_items() al abrir el diálogo).
        # OJO: el song hay que leerlo de row_items (ya sacado con takeItem
        # arriba), no con self.item(src, ...) — ese ítem ya no está en la
        # celda a esta altura y devolvería None (bug real: dejaba sin tags
        # cell a toda fila que pasara por un arrastre).
        song_item = row_items.get(_QUEUE_COL_SONG)
        song = song_item.data(_QUEUE_SONG_ROLE).song if song_item else None

        self.removeRow(src)
        self.insertRow(dst)
        for c, item in row_items.items():
            if item is not None:
                self.setItem(dst, c, item)
        if song is not None:
            self.setCellWidget(dst, _QUEUE_COL_TAGS, _TagsCell(song))
        self.selectRow(dst)


class _SongRef:
    """Envoltorio opaco para guardar el dict de la canción en un
    QTableWidgetItem: setData()/data() con Qt.UserRole hacen una copia de
    tipos "convertibles" para QVariant (dict, list, tuple...), así que la
    canción recuperada dejaba de ser el mismo objeto que self.playlist/
    self.play_queue y las comparaciones por identidad (`is`) del resto de la
    app fallaban en silencio. Un objeto sin conversión registrada no se
    copia: PyQt guarda el puntero al objeto Python tal cual."""
    __slots__ = ("song",)

    def __init__(self, song: dict):
        self.song = song


class _TagLineEdit(QLineEdit):
    """QLineEdit que avisa cuando pierde el foco (clic afuera / Tab) vía una
    señal propia, separada de Enter (returnPressed). editingFinished mezcla
    ambos casos en una sola señal y no alcanza para distinguir "confirmar"
    de "cancelar": un chip nuevo debe descartarse en el primer caso y
    agregarse en el segundo."""

    focus_lost = pyqtSignal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_lost.emit()


class _TagChip(QWidget):
    """Un tag individual dentro de la celda: doble clic lo edita sin tocar
    los demás (a diferencia de un solo QLineEdit por celda, que editaba el
    texto crudo completo de golpe). Vacío al confirmar = eliminarlo."""

    changed = pyqtSignal(str)
    removed = pyqtSignal()

    QSS = """
        QLabel#tag_label {
            background: rgba(126,84,175,60);
            border: 2px solid #B98CFF;
            border-radius: 6px;
            color: white;
            padding: 2px 8px;
        }
        QLineEdit#tag_edit {
            border: 2px solid #B98CFF;
            border-radius: 6px;
            background: rgba(0,0,0,0.4);
            color: white;
            padding: 1px 6px;
        }
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self.QSS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Fuente de verdad de "¿estoy editando?": no self.edit.isVisible(),
        # que depende de que toda la cadena de widgets padre (celda de
        # tabla incluida) ya esté "shown" — justo después de un rebuild()
        # eso no está garantizado todavía.
        self._editing = False

        self.label = QLabel(text)
        self.label.setObjectName("tag_label")
        self.edit = _TagLineEdit(text)
        self.edit.setObjectName("tag_edit")
        self.edit.setFixedWidth(90)
        self.edit.hide()
        self.edit.returnPressed.connect(self._commit)
        self.edit.focus_lost.connect(self._commit)

        layout.addWidget(self.label)
        layout.addWidget(self.edit)

    def mouseDoubleClickEvent(self, event):
        self.label.hide()
        self.edit.setText(self.label.text())
        self.edit.show()
        self.edit.setFocus()
        self.edit.selectAll()
        self._editing = True

    def _commit(self):
        if not self._editing:
            # Ya se confirmó: al esconderlo, focus_lost se dispara también
            # (perder el foco un widget oculto) y volvería a llamar esto.
            return
        self._editing = False
        text = self.edit.text().strip()
        self.edit.hide()
        self.label.show()
        if not text:
            self.removed.emit()
        elif text != self.label.text():
            self.label.setText(text)
            self.changed.emit(text)


class _AddTagChip(QWidget):
    """Chip "+ tag" al final de la fila: doble clic abre un campo vacío
    para agregar una tag nueva sin afectar las existentes. Enter confirma;
    un clic afuera se arrepiente y descarta lo escrito. Al abrir, muestra un
    dropdown con las 4 pistas (las que reconoce _apply_tag_mutes en
    audio_player.py) para elegir con un clic; sin seleccionar nada, el
    usuario puede escribir lo que quiera, tag sugerida o no."""

    # Mismo vocabulario que _TAG_TRACK_ALIASES en audio_player.py — no se
    # importa de ahí para no crear un import circular (audio_player ya
    # importa este módulo).
    TRACK_SUGGESTIONS = ["Batería", "Bajo", "Voz", "Otros"]

    added = pyqtSignal(str)

    QSS = """
        QLabel#tag_add_label {
            border: 2px dashed rgba(185,140,255,150);
            border-radius: 6px;
            color: rgba(255,255,255,150);
            padding: 2px 8px;
        }
        QLineEdit#tag_edit {
            border: 2px solid #B98CFF;
            border-radius: 6px;
            background: rgba(0,0,0,0.4);
            color: white;
            padding: 1px 6px;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self.QSS)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editing = False

        self.label = QLabel("+ tag")
        self.label.setObjectName("tag_add_label")
        self.edit = _TagLineEdit()
        self.edit.setObjectName("tag_edit")
        self.edit.setFixedWidth(90)
        self.edit.setPlaceholderText("nueva tag")
        self.edit.hide()
        self.edit.returnPressed.connect(self._commit)
        self.edit.focus_lost.connect(self._cancel)

        completer = QCompleter(self.TRACK_SUGGESTIONS, self.edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # activated (no highlighted): un clic en una opción agrega esa tag
        # de una, no solo la escribe y espera a que el usuario confirme.
        completer.activated.connect(self._pick_suggestion)
        self.edit.setCompleter(completer)
        self._completer = completer

        layout.addWidget(self.label)
        layout.addWidget(self.edit)

    def mouseDoubleClickEvent(self, event):
        self.label.hide()
        self.edit.clear()
        self.edit.show()
        self.edit.setFocus()
        self._editing = True
        self._completer.complete()  # dropdown con las 4 pistas, sin escribir nada

    def _pick_suggestion(self, text: str):
        self.edit.setText(text)
        self._commit()

    def _commit(self):
        if not self._editing:
            return
        self._editing = False
        text = self.edit.text().strip()
        self.edit.hide()
        self.label.show()
        if text:
            self.added.emit(text)

    def _cancel(self):
        if not self._editing:
            return  # _commit ya lo cerró; focus_lost es solo su eco
        self._editing = False
        self.edit.clear()
        self.edit.hide()
        self.label.show()


class _TagsCell(QWidget):
    """Fila de chips de una celda de Tags: cada uno se edita o elimina
    independiente de los demás, más un chip "+ tag" para agregar. Guarda
    los cambios directo en song['tags'] (misma coma-separada de siempre)."""

    def __init__(self, song: dict, parent=None):
        super().__init__(parent)
        self.song = song
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(4)
        self._rebuild()

    def _tags(self) -> list[str]:
        raw = self.song.get('tags', '')
        return [t.strip() for t in raw.split(',') if t.strip()]

    def _save(self, tags: list[str]):
        self.song['tags'] = ", ".join(tags)

    def _rebuild(self):
        while self._layout.count():
            child = self._layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        for i, tag in enumerate(self._tags()):
            chip = _TagChip(tag, self)
            chip.changed.connect(lambda new, idx=i: self._on_chip_changed(idx, new))
            chip.removed.connect(lambda idx=i: self._on_chip_removed(idx))
            self._layout.addWidget(chip)

        add_chip = _AddTagChip(self)
        add_chip.added.connect(self._on_tag_added)
        self._layout.addWidget(add_chip)
        self._layout.addStretch()

    def _on_chip_changed(self, idx: int, new_text: str):
        tags = self._tags()
        if idx < len(tags):
            tags[idx] = new_text
            self._save(tags)
        self._rebuild()

    def _on_chip_removed(self, idx: int):
        tags = self._tags()
        if idx < len(tags):
            del tags[idx]
            self._save(tags)
        self._rebuild()

    def _on_tag_added(self, text: str):
        tags = self._tags()
        tags.append(text)
        self._save(tags)
        self._rebuild()


class PlaybackQueueDialog(BaseDialog):
    """Administración de la cola de reproducción ("Agregar a la cola" del
    menú contextual de la playlist): grid con Canción/Duración/Tags,
    reordenable arrastrando filas, quitar canciones sin afectar la playlist.
    Edita audio_player.play_queue (y los "tags" de cada canción) en vivo,
    no hay Aceptar/Cancelar."""

    # Mismos valores que usa _QueueTable._move_row (definidos a nivel de
    # módulo para que ambas clases compartan uno solo sin acoplarse entre sí).
    SONG_ROLE = _QUEUE_SONG_ROLE
    COL_SONG, COL_DURATION, COL_TAGS = _QUEUE_COL_SONG, _QUEUE_COL_DURATION, _QUEUE_COL_TAGS

    TABLE_QSS = """
        QTableWidget#queue_table {
            background: rgba(255,255,255,0.1);
            color: white;
            font-size: 13px;
            gridline-color: rgba(255,255,255,0.15);
            border: 0px;
        }
        QTableWidget#queue_table::item {
            padding: 4px;
            background: rgba(0,0,0,0.35);
        }
        QTableWidget#queue_table::item:selected {
            background: #7E54AF;
            color: white;
        }
        QHeaderView::section {
            background: #3AABEF;
            color: white;
            font-weight: bold;
            border: 0px;
            padding: 4px;
        }
    """

    def __init__(self, audio_player, parent=None):
        self.audio_player = audio_player
        super().__init__(parent, "Administración de cola", (840, 525))
        self._setup_queue_ui()

    def _setup_queue_ui(self):
        hint = QLabel(
            "Arrastra una fila para reordenar. Supr o clic derecho para quitar "
            "de la cola. Doble clic en un tag lo edita (vacío al confirmar lo "
            "elimina), o en \"+ tag\" agregas uno nuevo: elige una pista del "
            "desplegable o escribe lo que quieras; Enter confirma, clic afuera "
            "cancela."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #cfcfe0; font-size: 12px;")

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        export_btn = QPushButton("⇩")
        export_btn.setObjectName("queue_export_btn")
        export_btn.setFixedSize(28, 28)
        export_btn.setToolTip(
            "Crear una playlist (Music List) a partir de las canciones en la cola"
        )
        export_btn.setStyleSheet("""
            QPushButton#queue_export_btn {
                background: rgba(126,84,175,60);
                border: 2px solid #B98CFF;
                border-radius: 6px;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#queue_export_btn:hover {
                background: rgba(126,84,175,120);
            }
        """)
        export_btn.clicked.connect(self.audio_player.export_queue_mlst)
        toolbar.addWidget(export_btn)

        self.table = _QueueTable(on_change=self._sync_order)
        self.table.setObjectName("queue_table")
        self.table.setStyleSheet(self.TABLE_QSS)
        self.table.setHorizontalHeaderLabels(["Canción", "Duración", "Tags"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_SONG, header.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_DURATION, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TAGS, header.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_item_menu)
        self._reload_items()

        close_btn = QPushButton()
        close_btn.setObjectName("cancelar_btn")
        close_btn.setFixedSize(70, 70)
        bg_image(close_btn, "images/split_dialog/cancelar_btn.png")
        close_btn.clicked.connect(self.accept)
        # Sin esto es el botón default del diálogo: Enter en el campo de una
        # tag nueva (o al editar una existente) también lo activaba y
        # cerraba todo el diálogo de golpe.
        close_btn.setAutoDefault(False)

        self.main_layout.addWidget(hint)
        self.main_layout.addLayout(toolbar)
        self.main_layout.addWidget(self.table)
        self.main_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _reload_items(self):
        self.table.setRowCount(0)
        for song in self.audio_player.play_queue:
            row = self.table.rowCount()
            self.table.insertRow(row)

            song_item = QTableWidgetItem(f"{song['artist']} - {song['song']}")
            song_item.setFlags(song_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            song_item.setData(self.SONG_ROLE, _SongRef(song))
            self.table.setItem(row, self.COL_SONG, song_item)

            duration_item = QTableWidgetItem(str(song.get('duration', '') or ''))
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, self.COL_DURATION, duration_item)

            self.table.setCellWidget(row, self.COL_TAGS, _TagsCell(song))

    def _show_item_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row == -1:
            return
        menu = QMenu(self.table)
        remove_action = menu.addAction("Quitar de la cola")
        action = menu.exec(self.table.mapToGlobal(pos))
        if action == remove_action:
            self.table.removeRow(row)
            self._sync_order()

    def _sync_order(self):
        self.audio_player.play_queue[:] = [
            self.table.item(r, self.COL_SONG).data(self.SONG_ROLE).song
            for r in range(self.table.rowCount())
        ]


class SplitDialog(BaseDialog):
    process_started = pyqtSignal(str, str, str, bool)
    dialog_closed = pyqtSignal()

    def __init__(self, parent=None):
        # 460 de alto: los widgets nativos de macOS son más altos y con 440
        # el botón MP3 quedaba pegado al textbox
        super().__init__(parent, "Dividir Canción", (360, 460))
        self._setup_split_ui()

    def _setup_split_ui(self):
        self.artist = QLineEdit()
        self.song = QLineEdit()
        self.song.setObjectName("SongText")
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Presiona 'Enter'...")

        file_btn = self._create_file_button()
        extract_btn = self._create_extract_button()
        btn_layout = self._create_action_buttons()

        # Layout
        self.main_layout.addWidget(file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addSpacing(20)
        self.main_layout.addWidget(self.file_path)
        self.main_layout.addWidget(extract_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(QLabel("Artista*"))
        self.main_layout.addWidget(self.artist)
        self.main_layout.addWidget(QLabel("Canción*"))
        self.main_layout.addWidget(self.song)
        self.main_layout.addWidget(self._create_timing_checkbox())
        self.main_layout.addLayout(btn_layout)

        self._setup_validation()

    def _create_timing_checkbox(self) -> QCheckBox:
        """Checkbox para medir cuánto tarda la separación (benchmark de hardware)."""
        self.timing_chk = QCheckBox("Cronometrar proceso")
        self.timing_chk.setChecked(False)
        self.timing_chk.setToolTip(
            "Al terminar la separación muestra el tiempo total que tomó el proceso"
        )
        # Mismos assets de checkbox que el resto de la app (incluyen la
        # palomita); el indicador default pierde la marca sobre el tema oscuro.
        unchecked = style_url('images/split_dialog/checkbox_unchecked.png')
        checked = style_url('images/split_dialog/checkbox_checked.png')
        hover = style_url('images/split_dialog/checkbox_hover01.png')
        hover_checked = style_url('images/split_dialog/checkbox_hover02.png')
        self.timing_chk.setStyleSheet(f"""
            QCheckBox {{ color: #cfcfe0; spacing: 8px; font-size: 12px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; image: url({unchecked}); }}
            QCheckBox::indicator:checked {{ image: url({checked}); }}
            QCheckBox::indicator:unchecked:hover {{ image: url({hover}); }}
            QCheckBox::indicator:checked:hover {{ image: url({hover_checked}); }}
        """)
        return self.timing_chk

    def _create_file_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("file_btn")
        btn.setFixedSize(200, 100)
        bg_image(btn, "images/split_dialog/mp3.png")
        btn.clicked.connect(self._select_file)
        return btn

    def _create_extract_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(120, 60)
        btn.setObjectName("extract_name_btn")
        bg_image(btn, "images/split_dialog/extract_name_btn.png")
        btn.clicked.connect(self._extract_name_from_file)
        return btn

    def _create_action_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.accept_btn = self._create_accept_button()
        cancel_btn = self._create_cancel_button()

        layout.addWidget(cancel_btn)
        layout.addWidget(self.accept_btn)
        return layout

    def _create_accept_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("aceptar_btn")
        btn.setFixedSize(70, 70)

        enabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn.png')
        ).replace('\\', '/')
        disabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn_disabled.png')
        ).replace('\\', '/')

        btn.setStyleSheet(f"""
            QPushButton#aceptar_btn{{
                image: url({enabled_path});
            }}
            QPushButton#aceptar_btn:disabled{{
                image: url({disabled_path});
            }}
        """)

        btn.clicked.connect(self._validate_and_start)
        return btn

    def _create_cancel_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("cancelar_btn")
        btn.setFixedSize(70, 70)
        bg_image(btn, "images/split_dialog/cancelar_btn.png")
        btn.clicked.connect(self.reject)
        return btn

    def _setup_validation(self):
        for field in [self.artist, self.song, self.file_path]:
            field.textChanged.connect(self._update_accept_button_state)
        self._update_accept_button_state()

    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de audio", "", AUDIO_INPUT_FILTER
        )
        if file_path:
            self.file_path.setText(file_path)

    def _update_accept_button_state(self):
        required_fields = [
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text().strip()
        ]
        self.accept_btn.setEnabled(all(required_fields))

    def _validate_and_start(self):
        if not Path(self.file_path.text()).exists():
            styled_message_box(
                self, "Error", "Archivo inválido",
                QMessageBox.Icon.Critical
            )
            return

        reply = styled_message_box(
            self,
            "Advertencia",
            "Dependiendo de su hardware, el proceso puede demorar varios minutos. ¿Continuar?",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_process()

    def _start_process(self):
        self.process_started.emit(
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text(),
            self.timing_chk.isChecked()
        )
        self.hide()
        self.dialog_closed.emit()

    def _extract_name_from_file(self):
        file_path = self.file_path.text()
        if not file_path:
            return

        filename = os.path.splitext(os.path.basename(file_path))[0]

        if '-' not in filename:
            return

        parts = filename.split('-')
        if len(parts) >= 2:
            artist = string.capwords(parts[0].strip())
            song = string.capwords(parts[-1].strip())

            self.artist.setText(artist)
            self.song.setText(song)

class CorrectSongDialog(BaseDialog):
    def __init__(self, parent=None, artist: str = "", song: str = ""):
        super().__init__(parent, "Corregir Artista/Canción", (360, 260))
        self._setup_correct_ui(artist, song)

    def _setup_correct_ui(self, artist: str, song: str):
        self.artist = QLineEdit(artist)
        self.song = QLineEdit(song)
        self.song.setObjectName("SongText")

        btn_layout = self._create_action_buttons()

        self.main_layout.addWidget(QLabel("Artista*"))
        self.main_layout.addWidget(self.artist)
        self.main_layout.addWidget(QLabel("Canción*"))
        self.main_layout.addWidget(self.song)
        self.main_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

        self._setup_validation()

    def _create_action_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.accept_btn = self._create_accept_button()
        cancel_btn = self._create_cancel_button()

        layout.addWidget(cancel_btn)
        layout.addWidget(self.accept_btn)
        return layout

    def _create_accept_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("aceptar_btn")
        btn.setFixedSize(70, 70)

        enabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn.png')
        ).replace('\\', '/')
        disabled_path = QDir.toNativeSeparators(
            resource_path('images/split_dialog/aceptar_btn_disabled.png')
        ).replace('\\', '/')

        btn.setStyleSheet(f"""
            QPushButton#aceptar_btn{{
                image: url({enabled_path});
            }}
            QPushButton#aceptar_btn:disabled{{
                image: url({disabled_path});
            }}
        """)

        btn.clicked.connect(self.accept)
        return btn

    def _create_cancel_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("cancelar_btn")
        btn.setFixedSize(70, 70)
        bg_image(btn, "images/split_dialog/cancelar_btn.png")
        btn.clicked.connect(self.reject)
        return btn

    def _setup_validation(self):
        for field in (self.artist, self.song):
            field.textChanged.connect(self._update_accept_button_state)
        self._update_accept_button_state()

    def _update_accept_button_state(self):
        self.accept_btn.setEnabled(
            bool(self.artist.text().strip() and self.song.text().strip())
        )

    def get_values(self) -> tuple[str, str]:
        return self.artist.text().strip(), self.song.text().strip()


class SongInfoDialog(BaseDialog):
    """Información de la canción y del archivo de origen que se separó.

    Artista y canción son las claves del propio data.json (las mismas con las
    que se arma la carpeta); el resto sale de su bloque "metadata", que escribe
    DemucsWorker al separar. Las canciones separadas antes de que ese bloque
    existiera no lo tienen: se muestran como "Desconocido".
    """

    UNKNOWN = "Desconocido"
    FIELDS = (
        ("Álbum", "album"),
        ("Año", "anio"),
        ("Género", "genero"),
        ("Formato", "formato"),
        ("Kbps", "kbps"),
    )

    def __init__(self, parent=None, artist: str = "", song: str = "",
                 metadata: dict | None = None):
        self._artist = artist
        self._song = song
        self._metadata = metadata or {}
        super().__init__(parent, "Información", (400, 390))
        self._setup_info_ui()

    def _setup_info_ui(self):
        # QLabel y no QTextEdit: son 6 campos fijos que siempre caben, y el
        # QTextEdit dibujaba una barra de desplazamiento inútil al lado.
        info = QLabel(self._build_html())
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setStyleSheet("""
            QLabel {
                color: #cfcfe0;
                background-color: rgba(0, 0, 0, 0.55);
                border: 0px;
                padding: 8px;
                font-size: 14px;
            }
        """)

        close_btn = QPushButton()
        close_btn.setObjectName("cancelar_btn")
        close_btn.setFixedSize(70, 70)
        bg_image(close_btn, "images/split_dialog/cancelar_btn.png")
        close_btn.clicked.connect(self.accept)

        self.main_layout.addWidget(info)
        self.main_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _build_html(self) -> str:
        # Ambas celdas llevan el mismo padding vertical: con padding solo en la
        # etiqueta, su línea base quedaba unos píxeles más abajo que el valor.
        cell = "padding:4px 0;"
        pairs = [
            ("Artista", self._escape(self._artist)),
            ("Canción", self._escape(self._song)),
            *((label, self._value(key)) for label, key in self.FIELDS),
        ]
        rows = "".join(
            f'<tr><td style="color:#F88FFF;{cell}padding-right:12px;">{label}</td>'
            f'<td style="{cell}">{value}</td></tr>'
            for label, value in pairs
        )
        return f'<table cellspacing="0" cellpadding="0">{rows}</table>'

    def _value(self, key: str) -> str:
        return self._escape(self._metadata.get(key, ""))

    def _escape(self, value) -> str:
        """Valor escapado, o "Desconocido" si viene vacío: los tags del archivo
        son texto libre ('AT&T', '<sic>') y el QLabel los renderiza como HTML."""
        text = str(value).strip()
        return html.escape(text) if text else self.UNKNOWN


class DownloadDialog(BaseDialog):
    download_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, "Descargar MP3 de YouTube", (400, 200))
        self._setup_validation()

    def _setup_ui(self):
        super()._setup_ui()

        # Ahora agregar nuestros widgets
        label = QLabel("Youtube URL:")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #3AABEF; font-size: 14px; font-weight: bold;")

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_edit.setStyleSheet("""
            QLineEdit {
                background: rgba(0,0,0,0.5);
                color: white;
                border: 1px solid #404040;
                border-radius: 5px;
                padding: 5px;
                font-size: 12px;
            }
        """)

        self.buttons = StyledButtons(self)
        self.buttons.yes_btn.clicked.connect(self._accept)
        self.buttons.no_btn.clicked.connect(self.reject)

        self.main_layout.addWidget(label)
        self.main_layout.addWidget(self.url_edit)
        self.main_layout.addWidget(self.buttons, alignment=Qt.AlignmentFlag.AlignCenter)

    def _setup_validation(self):
        self.url_edit.textChanged.connect(self._validate_url)
        self._validate_url()  # estado inicial

    def _validate_url(self):
        url = self.url_edit.text().strip()
        valid = (url.startswith('https://www.youtube.com') or
                 url.startswith('https://youtu.be'))
        self.buttons.setEnabled(valid)

    def _accept(self):
        url = self.url_edit.text().strip()
        self.download_requested.emit(url)
        self.accept()


def qr_pixmap(payload: str, size: int = 220) -> QPixmap | None:
    """QR del payload de emparejamiento; None si `qrcode` no está instalado.

    El import es perezoso a propósito: sin la librería el modo remoto sigue
    funcionando con los datos manuales que muestra el diálogo.
    """
    try:
        import qrcode
    except ImportError:
        return None
    try:
        img = qrcode.make(payload).convert("RGB")
    except Exception as e:
        logger.warning("No se pudo generar el QR: %s", e)
        return None
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3,
                  QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg).scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


class RemotePairDialog(BaseDialog):
    """Datos para emparejar PlayIt Mobile: QR + host/puerto/token manuales."""

    regenerate_requested = pyqtSignal()

    AVISO = (
        "Sólo funciona con el teléfono en la misma red Wi-Fi.\n"
        "Si Windows pregunta por el firewall (puede preguntar dos veces, por "
        "TCP y por UDP), hay que permitir el acceso en redes privadas.\n"
        "El código se conserva entre reinicios para que el teléfono reconecte "
        "solo; viaja sin cifrar por la red local, así que en una red pública "
        "conviene generar uno nuevo al terminar."
    )

    def __init__(self, parent=None, ip: str = "", port: int = 0, token: str = "",
                 name: str = ""):
        # Alto ≤ 600: split.png mide 960x600 y el fondo se repetiría al pasarse
        super().__init__(parent, "Modo remoto", (420, 600))
        # IP del teléfono que se emparejó, "" si el diálogo se cerró a mano
        self.paired_with = ""
        self._setup_pair_ui()
        self.set_pairing(ip, port, token, name)

    def on_paired(self, client_ip: str):
        """Un teléfono terminó de emparejarse: el QR ya no hace falta.

        Corre en el hilo GUI (la señal viene del hilo HTTP por conexión
        encolada). Cerrar dos veces es inofensivo, pero el primero es el que
        cuenta: `accept()` sobre un diálogo ya cerrado no hace nada.
        """
        self.paired_with = client_ip
        self.accept()

    def _setup_pair_ui(self):
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumHeight(220)
        self.qr_label.setStyleSheet("color: white;")

        self.address_label = self._data_label()
        self.token_label = self._data_label()
        self.token_label.setStyleSheet(
            self.token_label.styleSheet() + " font-family: monospace;"
        )

        aviso = QLabel(self.AVISO)
        aviso.setWordWrap(True)
        aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        aviso.setStyleSheet("color: #F88FFF; font-size: 11px;")

        self.regen_btn = QPushButton("Generar nuevo código")
        self.regen_btn.setObjectName("playlistToolBtn")
        self.regen_btn.setAutoDefault(False)
        self.regen_btn.setToolTip(
            "Reinicia el servidor con otro código: desempareja cualquier "
            "teléfono ya conectado"
        )
        self.regen_btn.clicked.connect(self.regenerate_requested)

        close_btn = QPushButton()
        close_btn.setObjectName("aceptar_btn")
        close_btn.setFixedSize(70, 70)
        close_btn.setAutoDefault(False)
        bg_image(close_btn, "images/split_dialog/aceptar_btn.png")
        close_btn.clicked.connect(self.accept)

        self.main_layout.addWidget(self.qr_label)
        self.main_layout.addWidget(self._caption("Dirección"))
        self.main_layout.addWidget(self.address_label)
        self.main_layout.addWidget(self._caption("Código"))
        self.main_layout.addWidget(self.token_label)
        self.main_layout.addWidget(aviso)
        self.main_layout.addStretch()
        self.main_layout.addWidget(self.regen_btn,
                                   alignment=Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(close_btn,
                                   alignment=Qt.AlignmentFlag.AlignCenter)

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        return label

    def _data_label(self) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Seleccionable para copiar y teclear en el móvil sin equivocarse
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        return label

    def set_pairing(self, ip: str, port: int, token: str, name: str = ""):
        """Refresca lo mostrado (también tras 'Generar nuevo código')."""
        from remote_server import format_token, pairing_payload

        self.address_label.setText(f"{ip}:{port}")
        self.token_label.setText(format_token(token))
        pixmap = qr_pixmap(pairing_payload(ip, port, token, name))
        if pixmap is None:
            self.qr_label.setText(
                "QR no disponible (falta el módulo qrcode).\n"
                "Emparejá escribiendo la dirección y el código."
            )
            self.qr_label.setWordWrap(True)
        else:
            self.qr_label.setPixmap(pixmap)
