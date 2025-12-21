import math

from PyQt6.QtCore import Qt, QPoint, QPointF, QSize, QRect,pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QDial
from resources import resource_path,bg_image



class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(35)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 0, 5, 0)

        # Título
        self.title = QLabel("Play It")
        self.title.setStyleSheet("color: white; font-weight: bold;")

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

        # Conexiones
        self.min_btn.clicked.connect(self.parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent.close)

        # Añadir elementos al layout
        self.layout.addWidget(self.title)
        self.layout.addStretch()
        self.layout.addWidget(self.min_btn)
        self.layout.addWidget(self.max_btn)
        self.layout.addWidget(self.close_btn)

        # Variables para arrastrar ventana
        self.draggable = True
        self.drag_position = QPoint()

    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.max_btn.setIcon(QIcon(resource_path('images/main_window/max.png')))
            self.max_btn.setIconSize(QSize(16, 16))
        else:
            self.parent.showMaximized()
            self.max_btn.setIcon(QIcon(resource_path('images/main_window/rest.png')))
            self.max_btn.setIconSize(QSize(16, 16))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.draggable:
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.draggable:
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


class CustomDial(QDial):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background = QPixmap(resource_path('images/main_window/dial_bg.png'))  # Imagen de fondo
        self.knob = QPixmap(resource_path('images/main_window/knob.png'))  # Imagen del knob

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

class SizeGrip(QWidget):
    def __init__(self, parent, position):
        super().__init__(parent)
        self.parent = parent
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
            self.window_pos = self.parent.pos()
            self.window_size = self.parent.size()
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

            self.parent.setGeometry(new_rect.normalized())
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

        # Conectar correctamente el cierre
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
        self.no_btn.setEnabled(on)
        bg_image(self.yes_btn, self._yes_normal if on else self._yes_disabled)
        bg_image(self.no_btn, self._no_normal if on else self._no_disabled)

