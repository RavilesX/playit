import os
import string
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QCheckBox, QPushButton,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QDir
from pathlib import Path
from resources import resource_path, styled_message_box,bg_image


class SplitDialog(QDialog):
    process_started = pyqtSignal(str, str, bool, str)
    dialog_closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dividir Canción")
        self.setFixedSize(400, 480)

        # Cargar archivo de estilos css
        with open('estilos.css', 'r') as file:
            style = file.read()
        self.setStyleSheet(style)

        self.artist = QLineEdit()
        self.song = QLineEdit()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Presiona 'Enter'...")
        self.gpu_check = QCheckBox("Usar GPU (Recomendado)")
        self.gpu_check.setChecked(True)
        check_enable = QDir.toNativeSeparators(resource_path('images/split_dialog/checkbox_checked.png')).replace('\\', '/')
        check_disabled = QDir.toNativeSeparators(resource_path('images/split_dialog/checkbox_unchecked.png')).replace(
            '\\', '/')
        check_enable_hover = QDir.toNativeSeparators(resource_path('images/split_dialog/checkbox_hover01.png')).replace('\\',
                                                                                                                  '/')
        check_disabled_hover = QDir.toNativeSeparators(
            resource_path('images/split_dialog/checkbox_hover02.png')).replace(
            '\\', '/')
        check_style = f"""
                            QCheckBox::indicator:checked{{
                                image: url({check_enable});
                            }}
                            QCheckBox::indicator:unchecked{{
                                image: url({check_disabled});
                            }}
                            QCheckBox::indicator:checked:hover,QCheckBox::indicator:checked:pressed{{
                                image: url({check_enable_hover});
                            }}
                            QCheckBox::indicator:unchecked:hover,QCheckBox::indicator:unchecked:pressed{{
                                image: url({check_disabled_hover});
                            }}
                            """
        self.gpu_check.setStyleSheet(check_style)

        self._init_ui()
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, self.width(), self.height())

        # Cargar imagen de fondo en el Qlabel
        bg_path = resource_path('images/split_dialog/split.png')
        pixmap = QPixmap(bg_path)

        if not pixmap.isNull():
            self.bg_label.setPixmap(pixmap)
        else:
            print(f"No se pudo cargar el background: {bg_path}")
        self.bg_label.lower()



    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Selección de archivo
        file_btn = QPushButton()
        file_btn.setObjectName("file_btn")
        file_btn.setFixedSize(200,100)
        bg_image(file_btn,"images/split_dialog/mp3.png")


        extract_name_btn = QPushButton()
        extract_name_btn.setFixedSize(120, 60)
        extract_name_btn.setObjectName("extract_name_btn")
        bg_image(extract_name_btn,"images/split_dialog/extract_name_btn.png")
        extract_name_btn.clicked.connect(self.extract_name)


        file_btn.clicked.connect(self._select_file)
        layout.addWidget(file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_path)
        layout.addWidget(extract_name_btn, alignment=Qt.AlignmentFlag.AlignCenter)


        # Campos obligatorios

        layout.addWidget(QLabel("Artista*"))
        layout.addWidget(self.artist)
        layout.addWidget(QLabel("Canción*"))
        layout.addWidget(self.song)

        # GPU Checkbox
        layout.addWidget(self.gpu_check)

        # Botones
        btn_layout = QHBoxLayout()
        self.accept_btn = QPushButton()
        self.accept_btn.setObjectName("aceptar_btn")
        self.accept_btn.setFixedSize(70, 70)
        path_enable = QDir.toNativeSeparators(resource_path('images/split_dialog/aceptar_btn.png')).replace('\\', '/')
        path_disabled = QDir.toNativeSeparators(resource_path('images/split_dialog/aceptar_btn_disabled.png')).replace('\\', '/')
        style = f"""
                    QPushButton#aceptar_btn{{
                        image: url({path_enable});
                    }}
                    QPushButton#aceptar_btn:disabled{{
                        image: url({path_disabled});
                    }}
                    """
        self.accept_btn.setStyleSheet(style)

        self.accept_btn.clicked.connect(self._validate)
        cancel_btn = QPushButton()
        cancel_btn.setObjectName("cancelar_btn")
        cancel_btn.setFixedSize(70, 70)
        bg_image(cancel_btn,"images/split_dialog/cancelar_btn.png")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.accept_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)


        # Validación en tiempo real
        self.artist.textChanged.connect(self._enable_accept)
        self.song.textChanged.connect(self._enable_accept)
        self.file_path.textChanged.connect(self._enable_accept)
        self._enable_accept()

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar MP3", "", "MP3 Files (*.mp3)")
        if path:
            self.file_path.setText(path)

    def _enable_accept(self):
        required = [
            self.artist.text().strip(),
            self.song.text().strip(),
            self.file_path.text().strip()
        ]
        self.accept_btn.setEnabled(all(required))

    def _validate(self):
        if not Path(self.file_path.text()).exists():
            styled_message_box(self, "Error", "Archivo inválido", QMessageBox.Icon.Critical)
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
            self.gpu_check.isChecked(),
            self.file_path.text()
        )
        self.hide()  # Oculta en lugar de cerrar
        self.dialog_closed.emit()  # Notificar que se ocultó
        #self.accept()

    def extract_name(self):
        teto=self.file_path.text()
        if not self.file_path.text():
            return

        # Obtener el nombre del archivo sin la ruta
        file = os.path.basename(self.file_path.text())

        # Separar nombre y extensión
        name, _ = os.path.splitext(file)

        # Verificar si hay guiones
        if '-' not in name:
            return

        # Dividir el nombre en partes usando guiones
        partes = name.split('-')

        # Construir resultados
        artist = partes[0]
        song = partes[-1]

        artist=artist.strip()
        song=song.strip()

        self.artist.setText(string.capwords(artist))
        self.song.setText(string.capwords(song))
