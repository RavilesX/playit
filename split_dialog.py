import os
import string

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QCheckBox, QPushButton,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path


class SplitDialog(QDialog):
    process_started = pyqtSignal(str, str, bool, str)
    dialog_closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dividir Canción")
        self.setFixedSize(400, 550)

        # Cargar archivo de estilos css
        with open('estilos.css', 'r') as file:
            style = file.read()
        self.setStyleSheet(style)

        self.artist = QLineEdit()
        self.song = QLineEdit()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Presiona 'Enter'...")
        # self.drums_check = QCheckBox("Batería")
        # self.drums_check.setChecked(True)
        # self.vocals_check = QCheckBox("Voces")
        # self.vocals_check.setChecked(True)
        # self.bass_check = QCheckBox("Bajo")
        # self.bass_check.setChecked(True)
        # self.guitar_radio = QRadioButton("Guitarra")
        # self.keyboard_radio = QRadioButton("Teclados")
        self.gpu_check = QCheckBox("Usar GPU (Recomendado)")
        self.gpu_check.setChecked(True)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Selección de archivo
        file_btn = QPushButton()
        file_btn.setObjectName("file_btn")
        file_btn.setFixedSize(200,100)

        extract_name_btn = QPushButton()
        extract_name_btn.setFixedSize(120, 60)
        extract_name_btn.setObjectName("extract_name_btn")
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

        # # Opciones de separación
        # layout.addWidget(QLabel("Pistas a incluir:"))
        # layout.addWidget(self.drums_check)
        # layout.addWidget(self.vocals_check)
        # layout.addWidget(self.bass_check)

        # Grupo de radios
        # radio_group = QButtonGroup(self)
        # radio_group.addButton(self.guitar_radio)
        # radio_group.addButton(self.keyboard_radio)
        # self.guitar_radio.setChecked(True)

        # radio_layout = QHBoxLayout()
        # radio_layout.addWidget(QLabel("Armonía:"))
        # radio_layout.addWidget(self.guitar_radio)
        # radio_layout.addWidget(self.keyboard_radio)
        # layout.addLayout(radio_layout)

        # GPU Checkbox
        layout.addWidget(self.gpu_check)

        # Botones
        btn_layout = QHBoxLayout()
        self.accept_btn = QPushButton()
        self.accept_btn.setObjectName("aceptar_btn")
        self.accept_btn.setFixedSize(70, 70)
        self.accept_btn.clicked.connect(self._validate)
        cancel_btn = QPushButton()
        cancel_btn.setObjectName("cancelar_btn")
        cancel_btn.setFixedSize(70, 70)

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
            QMessageBox.critical(self, "Error", "Archivo inválido")
            return

        reply = QMessageBox.question(
            self, "Advertencia",
            "Dependiendo de su hardware, el proceso puede demorar varios minutos. ¿Continuar?",
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
