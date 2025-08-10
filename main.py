import re
import os
import threading
from pathlib import Path

from einops.layers import torch

TORCH_AVAILABLE = False
import subprocess
import sys
import json
from datetime import datetime
import time
import pygame
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QPoint, QRect, QObject, QThread, QPointF, QUrl
from PyQt6.QtGui import QAction, QPixmap, QKeySequence, QColor, QPainter, QIcon,QDesktopServices
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QDockWidget, QTabWidget, QLabel, QTextEdit,
                             QPushButton, QSlider, QStatusBar, QMessageBox,
                             QProgressBar, QDialog, QLineEdit, QDial, QFrame, QListWidgetItem)
import shutil
from mutagen.mp3 import MP3
from PIL import Image
from split_dialog import SplitDialog
import io
import math
import requests
from urllib.parse import quote
import unicodedata
from resources import styled_message_box, bg_image, resource_path
from lazy_resources import LazyAudioManager, LazyImageManager, LazyLyricsManager, LazyPlaylistLoader
from lazy_config import LazyLoadingConfig, setup_production_lazy_loading

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sobre Playit")
        self.setFixedSize(450, 550)
        logo=resource_path('images/main_window/about.png')
        version=resource_path('images/main_window/version.png')
        about_text = f"""
        <style>
        li{{color:#b23c56;}}
        sub{{color:#c5c6c8;font-family: Arial, Helvetica, sans-serif;}}
        </style>
        <center><img src="{version}"></center>
        <p>Reproductor de Audio que permite separación de pistas usando Demucs.</p>
        <b>CARACTERISTICAS:</b>
        <p>A) Separación en 4 pistas:</p>
        <li>:: Batería</li>
        <li>:: Voz</li>
        <li>:: Bajo</li>
        <li>:: Demas instrumentos</li>
        <li>:: - Función de separar pistas en queue -</li>
        <li>:: - Proceso No bloqueante de la interfaz -</li>
        <p>B) Control de volumen General</p>
        <p>C) Control de volumen Individual para cada track</p>
        <li>:: Clic sobre el instrumento para mutear</li>
        <li>:: Slider para bajar o subir el volumen</li>
        <p>D) Botones para control de reproducción</p>
        <li>:: Reproducir anterior</li>
        <li>:: Play/Pausa</li>
        <li>:: Reproducir Siguiente</li>
        <li>:: Detener reproducción</li>
        <p>E) Barra indicadora de progreso</p>
        <p>F) Mostrar Portada/Cover de Album</p>
        <p>G) Mostrar Letras/Lyrics</p>
        <p>H) Playlist</p>
        <li>* Desacoplable, puede colocarse a la dercha o izquierda</li>
        <p>I) Barra de Estado con información útil</p>
        <p>J) Selección de Carpeta para cargar la Playlist</p>
        <p>K) Dividir audio</p>
        <li>:: Selección de archivo Mp3</li>
        <li>:: Botón para extraer desde el nombre de archivo el nombre de artista/canción</li>
        <li>:: Opción para usar GPU en caso de tener instalado GPU Nvidia y el software CUDA</li>
        <li>:: Una vez completada la division, se agrega a la carpeta 'music_library' y no se tiene que dividir de nuevo</li>
        <p>L) Eliminar pistas de la playlist</p>
        <p>M) Buscar en playlist</p>
        <p>N) Modificar Lyrics tempo de la cancion actual</p>
        <li>:: Adelantar la visualización 0.5 segundos</li>
        <li>:: Retrasar la visualización 0.5 segundos</li>
        <p>O) Limpiar la caché cargada</p>
        <sub>ESTE SOFTWARE SE PROPORCIONA 'TAL CUAL', SIN GARANTÍAS DE NINGÚN TIPO, YA SEAN EXPRESAS O IMPLÍCITAS, INCLUYENDO, PERO NO LIMITADO A, GARANTÍAS DE COMERCIABILIDAD, IDONEIDAD PARA UN PROPÓSITO PARTICULAR Y NO INFRACCIÓN. EN NINGÚN CASO, LOS AUTORES O COLABORADORES SERÁN RESPONSABLES DE DAÑOS DIRECTOS, INDIRECTOS, INCIDENTALES, ESPECIALES, EJEMPLARES O CONSECUENTES (INCLUYENDO, PERO NO LIMITADO A, LA ADQUISICIÓN DE BIENES O SERVICIOS SUSTITUTOS; LA PÉRDIDA DE USO, DATOS O BENEFICIOS; O LA INTERRUPCIÓN DEL NEGOCIO) DE CUALQUIER MANERA CAUSADOS Y BAJO CUALQUIER TEORÍA DE RESPONSABILIDAD, YA SEA POR CONTRATO, RESPONSABILIDAD ESTRICTA O AGRAVIO (INCLUYENDO NEGLIGENCIA O DE OTRA MANERA) QUE SURJA DE CUALQUIER FORMA DEL USO DE ESTE SOFTWARE, INCLUSO SI SE HA AVISADO DE LA POSIBILIDAD DE TALES DAÑOS.</sub>
        <p>Desarrollado por: RavilesX</p><p>Email: ravilesx@gmail.com</p>
        <p>Software Libre para uso personal</p>
        
        """

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setHtml(about_text)
        self.text_edit.setStyleSheet("""
                            QTextEdit {
                                color: #fc5490;
                                background: transparent;
                                border: 0px;
                                padding-top:2px;
                                font-size: 16px;                                
                            }
                        """)


        self.paypal_btn = QPushButton()
        self.paypal_btn.setFixedSize(70, 70)
        self.paypal_btn.setObjectName("aceptar_btn")
        bg_image(self.paypal_btn, "images/main_window/paypal.png")
        self.paypal_btn.clicked.connect(self.open_paypal_donation)

        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        layout.addWidget(QLabel("Se aceptan donaciones, por un mundo con software libre"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.paypal_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        # layout.addWidget(self.ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def open_paypal_donation(self):
        """Abre el enlace de PayPal en el navegador predeterminado"""
        paypal_url = QUrl("https://www.paypal.com/donate/?business=TULUZ868SK2BG&no_recurring=0&item_name=Desarrollo+apps+sin+fines+de+lucro%2C+no+necesitas+donar+para+usarlas%2C+pero+me+ayuda+y+me+inspira+a+seguir+creando+soluciones.&currency_code=USD")  # ¡REEMPLAZA CON TU ENLACE!

        if not paypal_url.isValid():
            print("¡Enlace de PayPal inválido!")
            return

        QDesktopServices.openUrl(paypal_url)

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
        self.min_btn.setIconSize(QSize(24, 24))
        self.max_btn = QPushButton()
        self.max_btn.setIcon(QIcon(resource_path('images/main_window/max.png')))
        self.max_btn.setIconSize(QSize(24, 24))
        self.close_btn = QPushButton()
        self.close_btn.setIcon(QIcon(resource_path('images/main_window/cerrar.png')))
        self.close_btn.setIconSize(QSize(32, 32))

        # Estilos de botones
        btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px 0px;
                border-radius:16px
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.2);
                border:5px solid transparent;
            }
            #close_btn:hover { background: #E81123; }
        """
        self.setStyleSheet(btn_style)
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
            self.max_btn.setIconSize(QSize(24, 24))
        else:
            self.parent.showMaximized()
            self.max_btn.setIcon(QIcon(resource_path('images/main_window/rest.png')))
            self.max_btn.setIconSize(QSize(24, 24))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.draggable:
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.draggable:
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


class SearchDialog(QDialog):
    search_requested = pyqtSignal(str)  # Señal para enviar el texto de búsqueda

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscar en Playlist")
        self.setFixedSize(300, 150)

        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Introduce texto a buscar...")
        self.btn_accept = QPushButton()
        self.btn_accept.setObjectName("aceptar_btn")
        self.btn_accept.setFixedSize(70, 70)
        bg_image(self.btn_accept,"images/split_dialog/aceptar_btn.png")
        self.btn_accept.clicked.connect(self.accept_search)
        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("cancelar_btn")
        bg_image(self.btn_cancel, "images/split_dialog/cancelar_btn.png")
        self.btn_cancel.setFixedSize(70, 70)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_accept.setDefault(True)
        self.btn_accept.setAutoDefault(True)

        layout = QVBoxLayout()
        layout.addWidget(self.search_text)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_accept)
        buttons.addWidget(self.btn_cancel)

        layout.addLayout(buttons)
        self.setLayout(layout)


    def accept_search(self):
        """Envía el texto y cierra el diálogo"""
        """Envía el texto sin limpiar el campo"""
        text = self.search_text.text().strip()
        if text:
            self.search_requested.emit(text)
        else:
            self.reject()


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


class AudioPlayer(QMainWindow):
    cover_loaded = pyqtSignal(QPixmap)
    lyrics_loaded = pyqtSignal(list)
    lyrics_error = pyqtSignal(str)
    lyrics_not_found = pyqtSignal()
    def __init__(self):
        super().__init__()

        self._setup_lazy_managers()

        # 1. Configuración básica de la ventana
        self._setup_window_properties()

        # 2. Inicializar variables de estado
        self._initialize_state_variables()

        # 3. Configurar audio y dependencias
        self._setup_audio_system()

        # 4. Crear y configurar la interfaz
        self._setup_user_interface()

        # 5. Configurar conexiones y eventos
        self._setup_connections()

        # 6. Inicializar timers y actualizaciones
        self._setup_timers()

        # 7. Validaciones finales
        self._perform_final_checks()

    def _setup_lazy_managers(self):
        """NUEVO: Inicializa los gestores de lazy loading"""
        self.lazy_audio = LazyAudioManager()
        self.lazy_images = LazyImageManager()
        self.lazy_lyrics = LazyLyricsManager()
        self.lazy_playlist = LazyPlaylistLoader()

        # Configuración automática
        config = LazyLoadingConfig.create_adaptive_config()
        setup_production_lazy_loading(self)

    def _setup_window_properties(self):
        """Configura propiedades básicas de la ventana principal."""
        # Configuración de ventana sin marco
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(resource_path('images/main_window/main_icon.png')))
        self.resize(1098, 813)
        self.center()

        # Configurar background y atributos de estilo
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Cargar y aplicar estilos CSS
        self._load_stylesheet()

    def _load_stylesheet(self):
        """Carga y aplica el archivo de estilos CSS."""
        try:
            with open('estilos.css', 'r') as file:
                style = file.read()
            self.setStyleSheet(style)
        except FileNotFoundError:
            print("Warning: estilos.css not found, using default styles")

    def _initialize_state_variables(self):
        """Inicializa todas las variables de estado de la aplicación."""
        # Variables de playlist y reproducción
        self.playlist = []
        self.current_index = -1
        self.playback_state = "Detenido"
        self.current_channels = []
        self.demucs_queue = []  # Cola de trabajos pendientes
        self.processing_multiple = False  # Indica si hay múltiples trabajos
        self.lyrics_lock = threading.Lock()

        # Variables de audio
        self.volume = 25
        self.individual_volumes = {
            "drums": 1.0,
            "vocals": 1.0,
            "bass": 1.0,
            "other": 1.0
        }
        self.mute_states = {
            "drums": False,
            "vocals": False,
            "bass": False,
            "other": False
        }

        # Variables de búsqueda
        self.search_index = 0
        self.search_results = []
        self.current_search = ""

        # Variables de procesamiento
        self.processing = False
        self.demucs_progress = 0
        self.demucs_active = False
        self.last_in_queue = {"artist":"","song":""}

        # Variables de diálogos
        self.split_dialog = None
        self.demucs_thread = None
        self.demucs_worker = None

        # Variables de letras
        self.lyrics = []

        # Variables de dependencias
        self._initialize_dependency_flags()

    def _initialize_dependency_flags(self):
        """Inicializa flags de disponibilidad de dependencias."""
        self.demucs_available = True
        self.pygame_available = True
        self.torch_available = True
        self.mutagen_available = True

    def _setup_audio_system(self):
        """Configura el sistema de audio y verifica dependencias."""
        # Inicializar Pygame Mixer
        self._initialize_pygame_mixer()

        # Cargar modelo Demucs (solo verificación)
        self.demucs_model = None
        self.load_demucs_model()

    def _initialize_pygame_mixer(self):
        """Inicializa el sistema de audio Pygame."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                pygame.mixer.set_num_channels(6)
        except pygame.error as e:
            print(f"Error initializing pygame mixer: {e}")
            self.pygame_available = False

    def _setup_user_interface(self):
        """Crea y configura todos los elementos de la interfaz de usuario."""
        # Crear frame principal y layout
        self._create_main_frame()

        # Configurar background
        self._setup_background()

        # Crear componentes principales
        self._create_title_bar()
        self._create_size_grips()
        self._create_tab_widget()
        self._create_progress_bar()
        self._create_control_buttons()
        self._create_track_controls()
        self._create_playlist_dock()

        # Configurar layout principal
        self._setup_main_layout()

        # Inicializar menú y barra de estado
        self.init_menu()
        self.init_status_bar()

    def _create_main_frame(self):
        """Crea el frame principal contenedor."""
        self.main_frame = QFrame()
        self.main_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)
        self.setCentralWidget(self.main_frame)

    def _create_title_bar(self):
        """Crea la barra de título personalizada."""
        self.title_bar = TitleBar(self)

    def _create_size_grips(self):
        """Crea los controles de redimensionamiento de ventana."""
        self.size_grips = {
            "top": SizeGrip(self, "top"),
            "bottom": SizeGrip(self, "bottom"),
            "left": SizeGrip(self, "left"),
            "right": SizeGrip(self, "right"),
            "top_left": SizeGrip(self, "top_left"),
            "top_right": SizeGrip(self, "top_right"),
            "bottom_left": SizeGrip(self, "bottom_left"),
            "bottom_right": SizeGrip(self, "bottom_right"),
        }

    def _create_tab_widget(self):
        """Crea el widget de pestañas para portada y letras."""
        # QTabWidget para portada y letras
        self.tabs = QTabWidget()
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyrics_text = QTextEdit()
        self.lyrics_text.setAcceptRichText(True)
        self.lyrics_text.setReadOnly(True)
        self.lyrics_font_size = 36
        self.tabs.addTab(self.cover_label, "Portada")
        self.tabs.addTab(self.lyrics_text, "Letras")
        self.cover_label.setPixmap(QPixmap(resource_path('images/main_window/none.png')))

    def _create_progress_bar(self):
        """Crea la barra de progreso de reproducción."""
        self.progress_song = QProgressBar(self)
        self.progress_song.setFormat("00:00 / 00:00")
        self.progress_song.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_song.setTextVisible(True)
        self.progress_song.setFixedHeight(20)
        self.progress_song.setEnabled(False)

    def _create_control_buttons(self):
        """Crea los botones de control de reproducción."""
        # Usar método existente pero renombrado para claridad
        self.controls_layout = self.init_leds()

    def _create_track_controls(self):
        """Crea los controles de pistas individuales."""
        # Usar método existente pero renombrado para claridad
        self.track_buttons_layout = self.track_buttons()

    def _create_playlist_dock(self):
        """Crea el dock de la playlist."""
        self.playlist_dock = QDockWidget(self)
        self.playlist_widget = QListWidget()
        self.playlist_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.playlist_widget.setFixedWidth(500)
        self.playlist_dock.setWidget(self.playlist_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.playlist_dock)

    def _setup_main_layout(self):
        """Configura el layout principal de la ventana."""
        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Añadir componentes al layout
        layout.addWidget(self.title_bar)
        layout.addWidget(self.tabs)
        layout.addLayout(self.track_buttons_layout)
        layout.addWidget(self.progress_song)
        layout.addLayout(self.controls_layout)

    def _setup_connections(self):
        """Configura todas las conexiones de señales y eventos."""
        # Conexiones de control de audio
        self._connect_playback_controls()

        # Conexiones de playlist
        self._connect_playlist_events()

        # Conexiones de dock
        self._connect_dock_events()

        # Conexiones para lazy loading
        self._connect_lazy_loading_signals()

    def _connect_lazy_loading_signals(self):
        """Configura las conexiones para lazy loading"""
        self.lazy_playlist.playlist_updated.connect(self._on_song_loaded)
        self.lazy_playlist.loading_finished.connect(self._on_playlist_loaded)
        self.cover_loaded.connect(self._handle_cover_loaded)
        self.lyrics_loaded.connect(self._handle_lyrics_loaded)
        self.lyrics_error.connect(self._handle_lyrics_error)
        self.lyrics_not_found.connect(self._handle_lyrics_not_found)
    def _connect_playback_controls(self):
        """Conecta los controles de reproducción."""
        self.play_btn.clicked.connect(self.toggle_play_pause)
        self.prev_btn.clicked.connect(self.play_previous)
        self.next_btn.clicked.connect(self.play_next)
        self.stop_btn.clicked.connect(self.stop_playback)

    def _connect_playlist_events(self):
        """Conecta eventos de la playlist."""
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected)
        self.playlist_widget.itemActivated.connect(self.play_selected)

    def _connect_dock_events(self):
        """Conecta eventos del dock de playlist."""
        self.playlist_dock.visibilityChanged.connect(self._update_playlist_menu_state)

    def _on_song_loaded(self, song_data):
        """Callback cuando se carga una canción individual"""
        # from PyQt6.QtWidgets import QListWidgetItem
        # from PyQt6.QtGui import QIcon
        # from resources import resource_path

        # Verificar si ya existe en la playlist
        exists = any(
            track['artist'] == song_data['artist'] and
            track['song'] == song_data['song']
            for track in self.playlist
        )

        if not exists:
            # Añadir a la playlist
            self.playlist.append(song_data)

            # Añadir a la UI
            icon = QIcon(resource_path('images/main_window/audio_icon.png'))
            item_text = f"{song_data['artist']} - {song_data['song']}"
            item = QListWidgetItem(item_text)
            item.setIcon(icon)
            self.playlist_widget.addItem(item)

            # Habilitar botones si es la primera canción
            if len(self.playlist) == 1:
                self.prev_btn.setEnabled(True)
                self.next_btn.setEnabled(True)
                self.play_btn.setEnabled(True)

            # Obtener letras de forma asíncrona
            self._check_and_fetch_lyrics_async(song_data['path'], song_data['artist'], song_data['song'])

    def _handle_cover_loaded(self, pixmap):
        self.cover_label.setPixmap(pixmap)

    def _handle_lyrics_loaded(self, lyrics_data):
        print("Lyrics cargados exitosamente")
        self.lyrics = lyrics_data

        if not hasattr(self, 'lyrics_timer'):
            self.lyrics_timer = QTimer(self)
            self.lyrics_timer.timeout.connect(self.update_lyrics_display)
        self.lyrics_timer.start(100)

        self.update_lyrics_menu_state()


    def _handle_lyrics_error(self, error_msg):
        print(f"Error cargando lyrics: {error_msg}")
        self.lyrics_text.setHtml(f'<center style="color: #ff6666;">Error: {error_msg}</center>')

    def _handle_lyrics_not_found(self):
        print("No se encontraron lyrics")
        self.lyrics_text.setHtml('<center style="color: #ff6666;">No hay letras disponibles</center>')

    def _on_playlist_loaded(self):
        """Callback cuando termina de cargar toda la playlist"""
        self.status_bar.showMessage(f"Playlist cargada: {len(self.playlist)} canciones")
        self.update_status()
        print(f"✅ Playlist loaded successfully: {len(self.playlist)} songs")

    def _setup_timers(self):
        """Configura los timers de actualización."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def _perform_final_checks(self):
        """Realiza validaciones finales y configuraciones post-inicialización."""
        # Validar dependencias
        self._check_dependencies()

        # Centrar ventana
        self.center()

        # Actualizar estado inicial
        self.update_status()

    def _setup_background(self):
        """Configura el background sin afectar la estructura existente"""
        # Crear QLabel para el background
        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.width(), self.height())

        # Cargar imagen
        bg_path = resource_path('images/main_window/background.png')
        pixmap = QPixmap(bg_path)

        if not pixmap.isNull():
            self.background_label.setPixmap(pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            print(f"No se pudo cargar el background: {bg_path}")

        # Asegurar que el background esté detrás de todo
        self.background_label.lower()

        # Estilo para el main_frame (transparente)
        self.main_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)

        # Ajustar cuando cambie el tamaño
        self.background_label.setScaledContents(True)

    def resizeEvent(self, event):
        """Redimensiona el background cuando cambia el tamaño de la ventana"""
        super().resizeEvent(event)
        if hasattr(self, 'background_label'):
            self.background_label.resize(self.size())

            # Volver a cargar la imagen para evitar pixelación
            bg_path = resource_path('images/main_window/background.png')
            pixmap = QPixmap(bg_path)
            if not pixmap.isNull():
                self.background_label.setPixmap(pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))


    def _check_dependencies(self):
        """Verifica que las dependencias requeridas están instaladas"""
        missing = []

        # Configuración para Windows
        if os.name == 'nt':
            kwargs = {
                'creationflags': subprocess.CREATE_NO_WINDOW,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE
            }
        else:  # Para otros sistemas operativos
            kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'start_new_session': True
            }

        # Verificar Demucs instalado globalmente
        try:
            subprocess.run(["demucs", "--help"],
                           **kwargs,
                           check=True,
                           text=True,
                           encoding='utf-8')
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Demucs no está instalado o no está en el PATH")

        # Verificar FFmpeg (requerido por Demucs)
        try:
            subprocess.run(["ffmpeg", "-version"],
                           **kwargs,
                           check=True,
                           text=True,
                           encoding='utf-8')
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("FFmpeg no está instalado o no está en el PATH")

        if missing:
            msg = "Faltan dependencias requeridas:\n\n" + "\n".join(missing)
            msg += "\n\nPor favor instale:\n1. Python 3.8+\n2. Demucs (pip install demucs)\n3. FFmpeg"
            styled_message_box(self, "Error crítico", msg,QMessageBox.Icon.Critical)
            sys.exit(1)

    def load_demucs_model(self):
        """Solo verifica que demucs está instalado, no carga el modelo"""
        try:
            # Primero verifica el PATH del sistema
            self._log_system_path()

            # Intenta encontrar demucs en Python
            self._check_python_environment()

            # Verificación directa con subprocess
            result = subprocess.run(
                ['demucs', '--help'],
                capture_output=True,
                text=True,
                shell=True  # Importante para Windows
            )

            if result.returncode != 0:
                raise RuntimeError(f"Demucs returned error: {result.stderr}")

            self.demucs_available = True

        except Exception as e:

            error_msg = f"Error checking Demucs: {str(e)}"
            print(error_msg)  # Para ver en consola si ejecutas con --console
            with open("demucs_error.log", "w") as f:
                f.write(error_msg)
            styled_message_box(
                self,
                "Error",
                f"No se pudo acceder a Demucs:\n{error_msg}\n\n"
                "Asegúrese que:\n"
                "1. Demucs está instalado (pip install demucs)\n"
                "2. Python está en el PATH del sistema\n"
                "3. El ejecutable se usa en la misma terminal donde funciona demucs"
            ,QMessageBox.Icon.Critical)
            self.demucs_available = False


    def _log_system_path(self):
        """Registra el PATH del sistema para debugging"""
        try:
            path = subprocess.run(
                ['cmd', '/c', 'echo', '%PATH%'],
                capture_output=True,
                text=True,
                shell=True
            ).stdout

        except Exception as e:
            with open("system_path.log", "w") as f:
                f.write(f"Error getting PATH: {str(e)}\n")

    def _check_python_environment(self):
        """Verifica la instalación de Python"""
        try:
            # Verifica donde está instalado Python
            python_path = subprocess.run(
                ['where', 'python'],
                capture_output=True,
                text=True,
                shell=True
            ).stdout

            # Verifica si demucs está en los paquetes
            pip_list = subprocess.run(
                ['pip', 'list'],
                capture_output=True,
                text=True,
                shell=True
            ).stdout

        except Exception as e:
            with open("python_environment.log", "w") as f:
                f.write(f"Error checking Python: {str(e)}\n")


    # def normalized_path(self, path):
    #     """Normaliza rutas para todos los sistemas operativos"""
    #     return Path(path).resolve().as_posix().lower()
    #
    # def _organize_demucs_output(self, demucs_dir, target_dir, input_path):
    #     """Reorganiza los archivos generados por Demucs"""
    #     try:
    #         # Crear directorio si no existe
    #         target_dir.mkdir(parents=True, exist_ok=True)
    #
    #         # Nombre base del archivo original (sin extensión)
    #         song_name = input_path.stem
    #
    #         for stem in ["drums", "bass", "other", "vocals"]:
    #             # Ruta de origen (archivo WAV generado por Demucs)
    #             src = self.normalized_path(demucs_dir / "separated/htdemucs_ft" / song_name / f"{stem}.mp3")
    #
    #             # Ruta de destino (MP3 convertido)
    #             dest = self.normalized_path(target_dir / "separated/")
    #
    #             #mover archivos
    #
    #             shutil.move(str(src),str(dest))
    #
    #         shutil.rmtree(demucs_dir/"separated/htdemucs_ft")
    #
    #
    #     except Exception as e:
    #         print(f"Error organizando archivos: {str(e)}")
    #         raise


    def init_leds(self):
        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName('prev_btn')
        self.prev_btn.setFixedSize(40, 40)
        self.prev_btn.setEnabled(False)
        bg_image(self.prev_btn,"images/main_window/prev.png")


        self.play_btn = QPushButton()
        self.play_btn.setObjectName('play_btn')
        self.play_btn.setFixedSize(80, 80)
        self.play_btn.setEnabled(False)
        bg_image(self.play_btn, "images/main_window/play.png")

        self.next_btn = QPushButton()
        self.next_btn.setObjectName('next_btn')
        self.next_btn.setFixedSize(40, 40)
        self.next_btn.setEnabled(False)
        bg_image(self.next_btn, "images/main_window/next.png")

        self.stop_btn = QPushButton()
        self.stop_btn.setObjectName('stop_btn')
        self.stop_btn.setFixedSize(40, 40)
        self.stop_btn.setEnabled(False)
        bg_image(self.stop_btn, "images/main_window/stop.png")

        self.volume_dial = CustomDial()
        self.volume_dial.setRange(0, 100)
        self.volume_dial.setValue(25)
        self.volume_dial.setFixedSize(120, 120)
        self.volume_dial.setNotchesVisible(True)
        self.volume_dial.valueChanged.connect(self.set_volume)


        # Layout
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.prev_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.volume_dial)

        return controls_layout


    def center(self):
        frame = self.frameGeometry()
        screen = self.screen().availableGeometry().center()
        frame.moveCenter(screen)
        self.move(frame.topLeft())


    def enable_disable_buttons(self, state):
        self.drums_btn.setEnabled(state)
        self.vocals_btn.setEnabled(state)
        self.bass_btn.setEnabled(state)
        self.other_btn.setEnabled(state)
        if state:
            # Solo actualizar si no están muteados
            for track_name, btn in zip(
                    ["drums", "vocals", "bass", "other"],
                    [self.drums_btn, self.vocals_btn, self.bass_btn, self.other_btn]
            ):
                if not self.mute_states[track_name]:
                    btn.setIcon(QIcon(resource_path(f'images/main_window/icons01/{track_name}.png')))
                    btn.setChecked(False)

    def track_buttons(self):
        # Configurar botones
        self.drums_btn = QPushButton()
        self.setup_button(self.drums_btn, 'drums_btn', 'drums')
        self.drums_slider = QSlider(Qt.Orientation.Horizontal)
        self.setup_slider(self.drums_slider, 'drums')

        self.vocals_btn = QPushButton()
        self.setup_button(self.vocals_btn, 'vocals_btn', 'vocals')
        self.vocals_slider = QSlider(Qt.Orientation.Horizontal)
        self.setup_slider(self.vocals_slider, 'vocals')

        self.bass_btn = QPushButton()
        self.setup_button(self.bass_btn, 'bass_btn', 'bass')
        self.bass_slider = QSlider(Qt.Orientation.Horizontal)
        self.setup_slider(self.bass_slider, 'bass')

        self.other_btn = QPushButton()
        self.setup_button(self.other_btn, 'other_btn', 'other')
        self.other_slider = QSlider(Qt.Orientation.Horizontal)
        self.setup_slider(self.other_slider, 'other')

        # Layout para cada instrumento (botón + slider)
        drums_layout = QVBoxLayout()
        drums_layout.addWidget(self.drums_btn)
        drums_layout.addWidget(self.drums_slider)

        vocals_layout = QVBoxLayout()
        vocals_layout.addWidget(self.vocals_btn)
        vocals_layout.addWidget(self.vocals_slider)

        bass_layout = QVBoxLayout()
        bass_layout.addWidget(self.bass_btn)
        bass_layout.addWidget(self.bass_slider)

        other_layout = QVBoxLayout()
        other_layout.addWidget(self.other_btn)
        other_layout.addWidget(self.other_slider)

        # Inicializar lista de botones mute
        self.mute_buttons = [
            self.drums_btn,
            self.vocals_btn,
            self.bass_btn,
            self.other_btn
        ]

        # Layout
        buttons_layout = QHBoxLayout()
        buttons_layout.addLayout(drums_layout)
        buttons_layout.addLayout(vocals_layout)
        buttons_layout.addLayout(bass_layout)
        buttons_layout.addLayout(other_layout)

        self.enable_disable_buttons(False)

        return buttons_layout

    def setup_slider(self, slider, track_name):
        """Configura los sliders de volumen individual"""
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedWidth(120)
        slider.valueChanged.connect(lambda value: self.set_individual_volume(track_name, value))

    def set_individual_volume(self, track_name, value):
        """Establece el volumen individual para cada pista"""
        # Guardar el volumen actual (antes de mute)
        self.individual_volumes[track_name] = value / 100.0

        # Si no está muteado, aplicar el volumen
        if not self.mute_states[track_name]:
            self.apply_volume_to_track(track_name, value / 100.0)

    def apply_volume_to_track(self, track_name, volume):
        """Aplica el volumen a la pista específica"""
        if not self.current_channels:
            return

        track_index = {
            "drums": 0,
            "vocals": 1,
            "bass": 2,
            "other": 3
        }.get(track_name)

        if track_index is not None and track_index < len(self.current_channels):
            self.current_channels[track_index].set_volume(volume * (self.volume / 100.0))

    def setup_button(self, button, object_name, icon_name):
        """Método para usar lazy loading de iconos"""
        button.setObjectName(object_name)
        button.setIconSize(QSize(120, 120))

        try:
            # Usar lazy loading para el icono
            icon_path = resource_path(f'images/main_window/icons01/{icon_name}.png')
            icon = self.lazy_images.load_icon_cached(icon_path, (120, 120))

            if icon.isNull():
                print(f"⚠️ Icono no encontrado: {icon_path}")
                # Crear icono por defecto
                default_pixmap = QPixmap(120, 120)
                default_pixmap.fill(Qt.GlobalColor.darkGray)
                icon = QIcon(default_pixmap)

            button.setIcon(icon)
        except Exception as e:
            print(f"❌ Error cargando icono para {object_name}: {e}")
            # Icono de emergencia
            fallback_pixmap = QPixmap(120, 120)
            fallback_pixmap.fill(Qt.GlobalColor.red)
            button.setIcon(QIcon(fallback_pixmap))

        button.setCheckable(True)
        button.clicked.connect(self.toggle_mute)

    def show_about_dialog(self):
        """Muestra el diálogo de información sobre la aplicación"""
        dialog = AboutDialog(self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()


    def keyPressEvent(self, event):
        """Maneja la tecla Delete para eliminar elementos seleccionados"""
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected()
        elif event.key() == Qt.Key.Key_Return and self.playlist_widget.currentItem():
            self.play_current()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        # Dibujar sombra exterior
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawRoundedRect(self.rect(), 8, 8)

    def init_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("Archivo")
        options_menu = menu.addMenu("Opciones")
        help_menu = menu.addMenu("Ayuda")

        load_action = QAction("Seleccionar Carpeta", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self.load_folder)
        file_menu.addAction(load_action)

        split_action = QAction("Dividir...", self)
        split_action.setShortcut(QKeySequence("Ctrl+D"))
        split_action.triggered.connect(self.show_split_dialog)
        file_menu.addAction(split_action)

        remove_action = QAction("Remover", self)
        remove_action.triggered.connect(self.remove_selected)
        file_menu.addAction(remove_action)

        # Opción Salir
        exit_action = QAction("&Salir", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Adios")
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)

        self.show_playlist_action = QAction("Mostrar lista", self)
        self.show_playlist_action.setCheckable(True)
        self.show_playlist_action.setChecked(True)
        self.show_playlist_action.triggered.connect(self._toggle_playlist_visibility)
        # show_playlist_action.triggered.connect(
        #     lambda: self.playlist_dock.setVisible(not self.playlist_dock.isVisible()))
        options_menu.addAction(self.show_playlist_action)

        # Opción de búsqueda
        search_action = QAction("&Buscar...", self)
        search_action.setStatusTip("Buscar en la playlist")
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self.show_search_dialog)
        options_menu.addAction(search_action)
        self.addAction(search_action)

        # Opción de modificar Lyrics
        lyrics_menu = options_menu.addMenu("Modificar Lyrics")
        self.advance_action = QAction(">> Mostrar Despues 0.5s", self)
        self.advance_action.setShortcut("Ctrl+Shift+Right")
        self.advance_action.triggered.connect(lambda: self.adjust_lyrics_timing(0.5))


        self.delay_action = QAction("<< Mostrar Antes 0.5s", self)
        self.delay_action.setShortcut("Ctrl+Shift+Left")
        self.delay_action.triggered.connect(lambda: self.adjust_lyrics_timing(-0.5))

        self.increase_font_action = QAction("Incrementar tamaño", self)
        self.increase_font_action.setShortcut("Ctrl+Shift+Up")
        self.increase_font_action.triggered.connect(self.increase_lyrics_font)

        self.decrease_font_action = QAction("Disminuir tamaño", self)
        self.decrease_font_action.setShortcut("Ctrl+Shift+Down")
        self.decrease_font_action.triggered.connect(self.decrease_lyrics_font)

        lyrics_menu.addAction(self.advance_action)
        lyrics_menu.addAction(self.delay_action)
        lyrics_menu.addAction(self.increase_font_action)
        lyrics_menu.addAction(self.decrease_font_action)

        cleanup_action = QAction("Limpiar Cache", self)
        cleanup_action.triggered.connect(self.cleanup_resources_manual)
        options_menu.addAction(cleanup_action)

        about_action = QAction("Sobre Playit", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        # Inicialmente deshabilitadas
        self.advance_action.setEnabled(False)
        self.delay_action.setEnabled(False)

    def increase_lyrics_font(self):
        """Aumenta el tamaño de la fuente en 2 puntos"""
        self.lyrics_font_size += 2
        if self.lyrics_font_size > 80:  # Límite máximo
            self.lyrics_font_size = 20
        self.apply_lyrics_font()

    def decrease_lyrics_font(self):
        """Disminuye el tamaño de la fuente en 2 puntos"""
        self.lyrics_font_size -= 2
        if self.lyrics_font_size < 20:  # Límite mínimo
            self.lyrics_font_size = 80
        self.apply_lyrics_font()

    def apply_lyrics_font(self):
        self.lyrics_text.setStyleSheet(f"""
                                    QTextEdit {{
                                        font-size: {self.lyrics_font_size}px;                                
                                    }}
                                """)

    def _toggle_playlist_visibility(self, state):
        """Maneja la acción del menú"""
        self.playlist_dock.setVisible(state)

    def _update_playlist_menu_state(self, visible):
        """Actualiza el menú cuando cambia la visibilidad del dock"""
        self.show_playlist_action.setChecked(visible)

    def closeEvent(self, event):
        if self.playlist_dock.isVisible():
            self.playlist_dock.close()
        super().closeEvent(event)

    def show_search_dialog(self):
        """Muestra el diálogo de búsqueda"""
        dialog = SearchDialog(self)

        bg_image(dialog,'images/split_dialog/split.png')
        dialog.search_requested.connect(self.handle_search)
        dialog.exec()



    def handle_search(self, search_text):
        """Maneja búsquedas manteniendo el estado anterior"""
        search_text = search_text.strip().lower()
        if not search_text:
            return

        # Solo reiniciar si es una nueva búsqueda
        if search_text != self.current_search:
            self.current_search = search_text
            self.search_results = [
                (i, self.playlist_widget.item(i).text().lower())
                for i in range(self.playlist_widget.count())
            ]
            self.search_results = [
                idx for idx, text in self.search_results
                if search_text in text
            ]
            self.search_index = 0  # Siempre comenzar desde el primero

        # Navegación ordenada
        if self.search_results:
            # Calcular índice relativo
            current_idx = self.search_results[self.search_index % len(self.search_results)]
            item = self.playlist_widget.item(current_idx)

            # Seleccionar y scroll
            self.playlist_widget.setCurrentItem(item)
            self.playlist_widget.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)

            # Incrementar para siguiente iteración
            self.search_index += 1

    # def select_search_result(self):
    #     """Selecciona el siguiente resultado en la lista"""
    #     if not self.search_results:
    #         return
    #
    #     # Obtener y seleccionar el ítem
    #     item = self.search_results[self.search_index]
    #     item.setSelected(True)
    #     self.playlist_widget.scrollToItem(item)
    #
    #
    #     # Actualizar índice para siguiente búsqueda
    #     self.search_index = (self.search_index + 1) % len(self.search_results)

    def show_split_dialog(self):
        """Muestra diálogo de forma no modal"""
        if not self.demucs_available:
            styled_message_box(self, "Función no disponible",
                                "La separación de pistas no está disponible (falta Demucs)",QMessageBox.Icon.Warning)
            return

        self.split_dialog = SplitDialog(self)
        self.split_dialog.process_started.connect(self.process_song)
        # Conectar al método existente
        self.split_dialog.show()


    def process_song(self, artist, song, use_gpu, file_path):
        """Agrega el trabajo a la cola y procesa si no hay trabajos activos"""
        # Crear objeto de trabajo
        job = {
            'artist': artist,
            'song': song,
            'use_gpu': use_gpu,
            'file_path': file_path
        }

        #Agrega o reemplaza la ultima cancion del queue
        self.last_in_queue["artist"] = artist
        self.last_in_queue["song"] = song

        # Agregar a la cola
        self.demucs_queue.append(job)

        # Si no hay proceso activo, iniciar procesamiento
        if not self.demucs_active:
            self._process_next_job()
        else:
            self.processing_multiple = True
            self.update_status()

    def _process_next_job(self):
        """Procesa el siguiente trabajo en la cola"""
        if not self.demucs_queue:
            self.demucs_active = False
            self.processing_multiple = False
            self.update_status()
            return

        # Obtener el próximo trabajo
        job = self.demucs_queue.pop(0)
        self._start_demucs_job(job)

    def _start_demucs_job(self, job):
        """Inicia un trabajo de separación con Demucs"""
        try:
            # Limpiar cualquier trabajo anterior
            self._cleanup_previous_job()

            self.demucs_active = True
            self.demucs_progress = 0
            self.processing = True
            self.update_status()

            # Crear worker y thread nuevos
            self.demucs_worker = DemucsWorker(
                job['artist'],
                job['song'],
                job['use_gpu'],
                job['file_path']
            )
            self.demucs_thread = QThread()

            # Configurar conexiones más simples
            self.demucs_worker.moveToThread(self.demucs_thread)
            self.demucs_thread.started.connect(self.demucs_worker.run)
            self.demucs_worker.finished.connect(self._on_demucs_success)
            self.demucs_worker.error.connect(self._handle_demucs_error)
            self.demucs_worker.progress.connect(self._update_demucs_progress)

            # Conexión de limpieza
            self.demucs_thread.finished.connect(self.demucs_thread.deleteLater)

            # Iniciar proceso
            self.demucs_thread.start()

        except Exception as e:
            self._handle_demucs_error(f"Error iniciando separación: {str(e)}")
            self._process_next_job()

    def _cleanup_previous_job(self):
        """Limpia recursos de trabajos anteriores"""
        try:
            if self.demucs_thread and self.demucs_thread.isRunning():
                self.demucs_thread.quit()
                self.demucs_thread.wait(1000)  # Esperar hasta 1 segundo
        except:
            pass

        try:
            if self.demucs_worker:
                self.demucs_worker.deleteLater()
        except:
            pass

        self.demucs_thread = None
        self.demucs_worker = None


    def _on_demucs_success(self):
        self.scan_folder(Path("music_library"))
        """Maneja la finalización exitosa de un trabajo"""
        # Primero limpiar el trabajo actual
        self._cleanup_current_job()

        # Procesar siguiente trabajo en la cola
        self._process_next_job()

        # Mostrar mensaje solo si fue el último trabajo
        if not self.demucs_queue and self.processing_multiple:
            self.processing_multiple = False
            self.audio_files = {'drums.mp3', 'vocals.mp3', 'bass.mp3', 'other.mp3'}

            self.verification_timer = QTimer(self)
            self.verification_timer.timeout.connect(self.check_files)
            self.verification_timer.start(30000)  # 30 segundos
            self.check_files()

    def check_files(self,):
        """Verifica si los archivos están disponibles"""
        for archivo in self.audio_files:
            file = f"music_library/{self.last_in_queue['artist']}/{self.last_in_queue['song']}/separated/{archivo}"
            if os.path.exists(file):
                self.verification_timer.stop()
                self.scan_folder(Path("music_library"))

    def _cleanup_current_job(self):
        """Limpia el trabajo actual sin afectar la cola"""
        self.demucs_active = False
        self.processing = False
        self.update_status()

        # Limpiar referencias
        if self.demucs_thread and self.demucs_thread.isRunning():
            self.demucs_thread.quit()
            self.demucs_thread.wait(500)  # Esperar medio segundo

        self.demucs_thread = None
        self.demucs_worker = None

    def _handle_demucs_error(self, error_msg):
        """Maneja errores y pasa al siguiente trabajo"""
        # Primero limpiar el trabajo actual
        self._cleanup_current_job()

        # Mostrar error solo si es el único trabajo
        if not self.processing_multiple:
            styled_message_box(self, "Error", error_msg, QMessageBox.Icon.Critical)

        # Continuar con el siguiente trabajo
        self._process_next_job()


    def _update_demucs_progress(self, value):
        """Actualiza el progreso del trabajo actual"""
        self.demucs_progress = value
        self.update_status()


    def _create_json(self, path, artist, song, config):
        data = {
            artist: {
                song: {
                    k: str(v) for k, v in config.items()
                }
            }
        }

        with open(path / "data.json", "w") as f:
            json.dump(data, f, indent=4)

    def close_application(self):
        """Cierra la aplicación completamente"""
        QApplication.instance().quit()


    def init_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status()

    def load_folder(self):
        """Método modificado para usar lazy loading"""
        from PyQt6.QtWidgets import QFileDialog
        from os.path import expanduser
        from pathlib import Path

        path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", expanduser("~/Music"))
        if path:
            # Limpiar playlist actual primero
            self.clear_playlist()

            # Mostrar indicador de carga
            self.status_bar.showMessage("Cargando playlist...")

            # Usar lazy loading para cargar la carpeta
            try:
                self.lazy_playlist.load_playlist_lazy(Path(path))
                print(f"🔄 Started loading playlist from: {path}")
            except Exception as e:
                print(f"❌ Error starting playlist load: {e}")
                styled_message_box(self, "Error", f"Error iniciando carga: {str(e)}", QMessageBox.Icon.Critical)
                self.status_bar.showMessage("Error cargando playlist")

    def reset_search_indices(self):
        """Reinicia los índices y resultados de búsqueda"""
        self.search_results = []
        self.search_index = 0
        self.current_search = ""

    def clear_playlist(self):
        """Limpia la playlist actual"""
        self.stop_playback()
        self.playlist.clear()
        self.playlist_widget.clear()
        self.current_index = -1
        self.reset_search_indices()

        # Deshabilitar botones
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

    def scan_folder(self, path):
        self.reset_search_indices()
        icon = QIcon(resource_path('images/main_window/audio_icon.png'))
        for json_file in path.rglob("*.json"):
            with open(json_file, "r") as f:
                try:
                    data = json.load(f)
                    dir_path = json_file.parent
                    for artist, songs in data.items():
                        for song, _ in songs.items():
                            exist = False
                            for track in self.playlist:
                                if (track['artist'] == artist and track['song']==song):
                                    exist=True
                                    break
                            if not exist:
                                self.playlist.append({
                                    "artist": artist,
                                    "song": song,
                                    "path": dir_path
                                })
                                item = QListWidgetItem(f"{artist} - {song}")
                                item.setIcon(icon)
                                self.playlist_widget.addItem(item)
                                if not self.prev_btn.isEnabled():
                                    self.prev_btn.setEnabled(True)
                                    self.next_btn.setEnabled(True)
                                    self.play_btn.setEnabled(True)
                                self._check_and_fetch_lyrics_async(dir_path, artist, song)
                except Exception as e:
                    styled_message_box(self, "Error", f"Error cargando {json_file}: {str(e)}",QMessageBox.Icon.Critical)
        self.update_status()

    def _check_and_fetch_lyrics_async(self, dir_path, artist, song):
        """Versión asíncrona de _check_and_fetch_lyrics"""

        def check_lyrics():
            lrc_path = dir_path / "lyrics.lrc"
            default_text = "Letras no encontradas, revisa datos de artista/canción"

            needs_update = False
            if not lrc_path.exists():
                needs_update = True
            else:
                try:
                    with open(lrc_path, "r", encoding="utf-8") as f:
                        if default_text in f.read():
                            needs_update = True
                except:
                    needs_update = True

            if needs_update:
                self._fetch_lyrics_from_api(artist, song, dir_path)

        # Ejecutar en un hilo separado para no bloquear

        thread = threading.Thread(target=check_lyrics, daemon=True)
        thread.start()

    def _normalize_text(self, text):
        """Normaliza texto removiendo tildes y convirtiendo a minúsculas"""
        normalized = unicodedata.normalize('NFKD', text.lower())
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

    def _fetch_lyrics_from_api(self, artist, song, output_dir):
        """Consulta la API de LRC Lib y genera el archivo"""
        base_url = "https://lrclib.net/api/search"
        query = f"{artist} {song}".replace(" ", "+")
        url = f"{base_url}?q={quote(query)}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            results = response.json()

            # Normalizar valores de referencia
            norm_artist = self._normalize_text(artist)
            norm_song = self._normalize_text(song)

            synced_lyrics = ""
            for result in results:
                # Normalizar valores de la API
                api_artist = self._normalize_text(result.get("artistName", ""))
                api_song = self._normalize_text(result.get("trackName", ""))

                if (api_artist == norm_artist and
                        api_song == norm_song and
                        result.get("syncedLyrics")):
                    synced_lyrics = result["syncedLyrics"]
                    break
            self._write_lyrics_file(output_dir, artist, song, synced_lyrics)

        except Exception as e:
            print(f"Error API: {str(e)}")
            self._write_lyrics_file(output_dir, artist, song, None)

    def _write_lyrics_file(self, output_dir, artist, song, lyrics):
        """Escribe el archivo LRC con formato, centrando todas las líneas"""
        # Línea de título (manteniendo el formato actual)
        title_line = f'[00:00.00]<H1 style="color: #3AABEF;"><center>{artist}</center></H1>\n<H2 style="color: #7E54AF;"><center>{song}</center></H2>\n'

        if not lyrics:
            # Caso sin letras
            content = title_line + '<center style="color: #ff2626;">Letras no encontradas, revisa datos de artista/canción</center>\n'
        else:
            # Procesar cada línea de letras
            processed_lines = []
            for line in lyrics.split('\n'):
                if line.strip():  # Solo procesar líneas no vacías
                    # Dividir en timestamp y texto
                    parts = line.split(']', 1)
                    if len(parts) == 2:
                        timestamp, text = parts
                        # Reconstruir la línea con el texto centrado
                        processed_line = f'{timestamp}]<center style="color: #F88FFF;">{text.strip()}</center>'
                        processed_lines.append(processed_line)

            # Unir el contenido
            content = title_line + '\n'.join(processed_lines) + '\n'

        # Escribir el archivo
        with open(output_dir / "lyrics.lrc", "w", encoding="utf-8") as f:
            f.write(content)

    def play_selected(self):
        self.stop_playback()
        self.current_index = self.playlist_widget.currentRow()
        self.play_current()

    def _control_channels(self, action: str):
        """Control centralizado para operaciones en los canales de audio.
        Acciones soportadas: 'play', 'stop', 'pause', 'unpause'
        """
        if not self.current_channels:
            print(f"⚠️ No hay canales para acción: {action}")
            return


        for i, channel in enumerate(self.current_channels):
            if not channel:
                continue

            if action == 'play':
                channel.unpause()
            elif action == 'stop':
                channel.stop()
            elif action == 'pause':
                channel.pause()
            elif action == 'unpause':
                channel.unpause()

        print(f"🎮 Acción de control aplicada: {action} a {len(self.current_channels)} canales")


    def _setup_audio(self) -> bool:
        """Método para usar lazy loading de audio"""
        if not (0 <= self.current_index < len(self.playlist)):
            return False

        song = self.playlist[self.current_index]
        path = Path(song["path"])

        try:
            print(f"🔄 Cargando audio para: {song['artist']} - {song['song']}")

            # Usar lazy loading para cargar los sonidos
            sounds = self.lazy_audio.load_audio_lazy(path)

            if not sounds:
                print(f"❌ No se pudieron cargar los archivos de audio para: {path}")
                from PyQt6.QtWidgets import QMessageBox
                from resources import styled_message_box
                styled_message_box(
                    self,
                    "Error de Audio",
                    f"No se encontraron las pistas separadas para:\n{song['artist']} - {song['song']}\n\n"
                    "Asegúrese de que exista la carpeta 'separated' con los archivos:\n"
                    "• drums.mp3\n• vocals.mp3\n• bass.mp3\n• other.mp3",
                    QMessageBox.Icon.Warning
                )
                return False

            print(f"✅ Audio cargado: {len(sounds)} pistas")

            # Crear canales de reproducción
            self.current_channels = []
            for i, sound in enumerate(sounds):
                try:
                    channel = sound.play()
                    channel.pause()  # Pausar inmediatamente para control manual
                    self.current_channels.append(channel)
                except Exception as e:
                    print(f"❌ Error creando canal {i}: {e}")
                    return False

            # Aplicar volúmenes iniciales
            for i, track_name in enumerate(["drums", "vocals", "bass", "other"]):
                if i < len(self.current_channels):
                    volume = 0 if self.mute_states[track_name] else (
                            self.individual_volumes[track_name] * (self.volume / 100.0)
                    )
                    self.current_channels[i].set_volume(volume)

            # Configurar barra de progreso
            try:
                length_seconds = sounds[0].get_length()
                length_ms = int(length_seconds * 1000)
                total_mins, total_secs = divmod(int(length_seconds), 60)

                self.progress_song.setFormat(f"00:00 / {total_mins:02d}:{total_secs:02d}")
                self.progress_song.setRange(0, length_ms)
                self.progress_song.setValue(0)

                print(f"⏱️ Duración configurada: {total_mins:02d}:{total_secs:02d}")
            except Exception as e:
                print(f"⚠️ Error configurando progreso: {e}")

            return True

        except Exception as e:
            print(f"❌ Error general en _setup_audio: {e}")
            from PyQt6.QtWidgets import QMessageBox
            from resources import styled_message_box
            styled_message_box(
                self,
                "Error",
                f"Error cargando audio: {str(e)}",
                QMessageBox.Icon.Critical
            )
            return False

    def _update_playback_ui(self, state: str):
        """Actualiza la UI según el estado de reproducción"""

        self.stop_btn.setEnabled(state != "Detenido")
        self.progress_song.setEnabled(state != "Detenido")
        self.playback_state = state

        if self.current_index!=-1:
            song = self.playlist[self.current_index]
            path = song["path"]


        # Habilitar botones
        self.drums_btn.setEnabled(True)
        self.vocals_btn.setEnabled(True)
        self.bass_btn.setEnabled(True)
        self.other_btn.setEnabled(True)


        self.update_status()

    def _restore_mute_states(self):
        """Actualiza los botones según los estados de mute guardados"""
        # Configurar iconos basados en los estados actuales
        icon_map = {
            "drums": ("drums", "no_drums"),
            "vocals": ("vocals", "no_vocals"),
            "bass": ("bass", "no_bass"),
            "other": ("other", "no_other")
        }

        for track_name, btn in zip(
                ["drums", "vocals", "bass", "other"],
                [self.drums_btn, self.vocals_btn, self.bass_btn, self.other_btn]
        ):
            # Establecer el icono correcto basado en el estado de mute
            icon_index = 1 if self.mute_states[track_name] else 0
            icon_name = icon_map[track_name][icon_index]
            btn.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))

            # Sincronizar el estado visual del botón
            btn.setChecked(self.mute_states[track_name])

    def play_current(self):
        print(f"▶️ Iniciando reproducción...")

        # Detener reproducción actual
        self.stop_playback()

        if not (0 <= self.current_index < len(self.playlist)):
            print("❌ Índice de playlist inválido")
            return

        # Configurar audio
        if not self._setup_audio():
            print("❌ Falló la configuración de audio")
            return

        print(
            f"🎵 Reproduciendo: {self.playlist[self.current_index]['artist']} - {self.playlist[self.current_index]['song']}")

        # Restaurar estados de mute
        self._restore_mute_states()

        # Iniciar reproducción
        self._control_channels('play')

        # Actualizar metadatos (portada, letras, etc.)
        self._update_metadata()

        # Actualizar UI
        self._update_playback_ui('Activa')
        self.playback_state = "Activa"

        # Aplicar volumen
        self.set_volume(self.volume)

        # Actualizar menú de letras
        self.update_lyrics_menu_state()

        print("✅ Reproducción iniciada correctamente")






    def toggle_play_pause(self):
        if self.playback_state == "Activa":
            self._control_channels('pause')
            self._update_playback_ui('Pausada')
            self.playback_state = "Pausada"
        else:
            self._control_channels('unpause')
            self._update_playback_ui('Activa')
            self.playback_state = "Activa"
        self.update_lyrics_menu_state()

    def stop_playback(self):
        time.sleep(100 / 1000)    # Evita que haya un arrastre cuando se cambia de cancion abruptamente
        self._control_channels('stop')
        self._update_playback_ui('Detenido')
        self.playback_state = "Detenido"
        self.cover_label.setPixmap(QPixmap(resource_path('images/main_window/none.png')))
        self.progress_song.setValue(0)
        self.current_channels = []
        self.update_lyrics_menu_state()

    def _update_metadata(self):
        """Método corregido para usar lazy loading de imágenes y letras"""
        try:
            song = self.playlist[self.current_index]
            path = Path(song["path"])
            lrc_path = path / "lyrics.lrc"

            # Actualizar título de ventana
            title = f"{song['artist']} - {song['song']}"
            self.title_bar.title.setText(title)
            print(f"📝 Título actualizado: {title}")

            # Cargar portada usando lazy loading (async)
            def load_cover_async():
                try:
                    cover_pixmap = self.lazy_images.load_cover_lazy(path, (500, 500))
                    self.cover_loaded.emit(cover_pixmap)
                    print("🖼️ Portada cargada")
                except Exception as e:
                    print(f"❌ Error cargando portada async: {e}")

            def load_lyrics_async():
                try:
                    # Verificar si el archivo existe primero
                    if not lrc_path.exists():
                        self.lyrics_not_found.emit()
                        return

                    # Usar el lazy manager para cargar las letras
                    lyrics_data = self.lazy_lyrics.load_lyrics_lazy(path)
                    self.lyrics_loaded.emit(lyrics_data)


                except Exception as e:
                    print(f"❌ Error cargando letras: {e}")
                    self.lyrics_error.emit(str(e))

             # Ejecutar carga asíncrona
            threading.Thread(target=load_cover_async, daemon=True).start()
            threading.Thread(target=load_lyrics_async, daemon=True).start()

            # Precargar recursos de las siguientes canciones
            self._preload_adjacent_resources()

        except Exception as e:
            print(f"❌ Error actualizando metadatos: {e}")

    def get_cache_stats(self) -> dict:
        """Obtiene estadísticas completas de uso de cache"""
        try:
            audio_stats = self.lazy_audio.cache.get_stats()
            image_stats = self.lazy_images.cache.get_stats()
            lyrics_stats = self.lazy_lyrics.cache.get_stats()

            total_hits = audio_stats['hits'] + image_stats['hits'] + lyrics_stats['hits']
            total_requests = total_hits + audio_stats['misses'] + image_stats['misses'] + lyrics_stats['misses']

            return {
                "audio_cache": audio_stats,
                "image_cache": image_stats,
                "lyrics_cache": lyrics_stats,
                "total_cached_items": (
                        audio_stats['size'] + image_stats['size'] + lyrics_stats['size']
                ),
                "overall_hit_rate": (total_hits / max(1, total_requests) * 100),
                "memory_utilization": {
                    "audio": audio_stats['utilization'],
                    "images": image_stats['utilization'],
                    "lyrics": lyrics_stats['utilization']
                }
            }
        except Exception as e:
            print(f"❌ Error obteniendo estadísticas: {e}")
            return {
                "error": str(e),
                "total_cached_items": 0,
                "overall_hit_rate": 0,
                "memory_utilization": {"audio": 0, "images": 0, "lyrics": 0}
            }


    def _preload_adjacent_resources(self):
        """Precarga recursos de canciones adyacentes de forma optimizada"""
        if not self.playlist:
            return

        def preload_worker():
            try:
                print("🔄 Iniciando precarga de recursos adyacentes...")

                # Precargar audio de las siguientes 2 canciones
                self.lazy_audio.preload_next_songs(self.playlist, self.current_index, count=2)

                # Precargar letras de canciones adyacentes
                self.lazy_lyrics.preload_lyrics(self.playlist, self.current_index)

                # Precargar portadas de canciones adyacentes
                for offset in [-1, 1]:
                    try:
                        idx = (self.current_index + offset) % len(self.playlist)
                        if 0 <= idx < len(self.playlist):
                            song_path = Path(self.playlist[idx]["path"])
                            cache_key = f"cover_{song_path}_(500, 500)"

                            # Solo precargar si no está en cache
                            if cache_key not in self.lazy_images.cache._cache:
                                self.lazy_images.load_cover_lazy(song_path, (500, 500))
                                print(
                                    f"🖼️ Portada precargada: {self.playlist[idx]['artist']} - {self.playlist[idx]['song']}")
                    except Exception as e:
                        print(f"❌ Error precargando portada {offset}: {e}")

                print("✅ Precarga completada")

            except Exception as e:
                print(f"❌ Error en precarga general: {e}")

        # Ejecutar en hilo separado para no bloquear
        threading.Thread(target=preload_worker, daemon=True).start()

    def cleanup_resources_manual(self):
        """Limpia recursos manualmente y muestra estadísticas"""
        try:
            print("🧹 Iniciando limpieza manual de recursos...")

            # Obtener estadísticas antes
            before_stats = self.get_cache_stats()
            print(f"📊 Antes - Total elementos: {before_stats['total_cached_items']}")

            # Limpiar caches
            self.lazy_audio.cache.clear()
            self.lazy_images.cache.clear()
            self.lazy_lyrics.cache.clear()

            # Obtener estadísticas después
            after_stats = self.get_cache_stats()
            print(f"📊 Después - Total elementos: {after_stats['total_cached_items']}")

            # Mostrar mensaje al usuario
            styled_message_box(
                self,
                "Limpieza Completa",
                f"Cache limpiado exitosamente.\n"
                f"Elementos eliminados: {before_stats['total_cached_items'] - after_stats['total_cached_items']}\n"
                f"Memoria liberada aproximada: {(before_stats['total_cached_items'] - after_stats['total_cached_items']) * 2:.1f}MB",
                QMessageBox.Icon.Information
            )

            print("✅ Limpieza manual completada")

        except Exception as e:
            print(f"❌ Error en limpieza manual: {e}")
            styled_message_box(
                self,
                "Error",
                f"Error durante la limpieza: {str(e)}",
                QMessageBox.Icon.Warning
            )


    def load_lyrics(self, file_path):

        self.lyrics = []
        current_time = None
        current_text = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Buscar timestamp [mm:ss.xx]
                time_match = re.match(r'\[(\d+):(\d+\.\d+)\]', line)

                if time_match:
                    # Guardar el bloque anterior
                    if current_time is not None:
                        self.lyrics.append((current_time, '\n'.join(current_text)))

                    # Nuevo timestamp
                    minutos = int(time_match.group(1))
                    segundos = float(time_match.group(2))
                    current_time = minutos * 60 + segundos
                    current_text = [line[time_match.end():]]
                else:
                    # Línea sin timestamp: agregar al texto actual
                    if current_time is not None and line:
                        current_text.append(line)

            # Agregar el último bloque
            if current_time is not None:
                self.lyrics.append((current_time, '\n'.join(current_text)))

        # Actualizar al cargar lyrics
        self.update_lyrics_menu_state()

        # Conectar al temporizador de actualización
        self.lyrics_timer = QTimer(self)
        self.lyrics_timer.timeout.connect(self.update_lyrics_display)
        self.lyrics_timer.start(100)  # Actualizar cada 100ms

    def update_lyrics_display(self):
        """Actualiza el texto según el tiempo actual de reproducción"""
        try:
            if not self.lyrics or not self.playback_state == "Activa":
                return

            # Obtener tiempo actual en segundos con decimales
            current_time = self.progress_song.value() / 1000.0

            # Buscar la letra correspondiente
            current_lyric = None
            for time_stamp, text in self.lyrics:
                if current_time >= time_stamp:
                    current_lyric = text
                else:
                    break  # Los lyrics están ordenados, podemos salir


            # Solo actualizar si hay un lyric válido y es diferente al anterio
            if current_lyric and current_lyric != getattr(self, 'last_lyric', None):
                self.lyrics_text.setHtml(current_lyric)
                self.last_lyric = current_lyric

        except Exception as e:
            print(f"❌ Error actualizando letras: {e}")

    def update_lyrics_menu_state(self):
        """Actualiza el estado de las opciones del menú"""
        enabled = (
                self.playback_state == "Activa" and
                self.current_index != -1 and
                not self._lyrics_has_error()
        )
        self.advance_action.setEnabled(enabled)
        self.delay_action.setEnabled(enabled)

    def _lyrics_has_error(self):
        """Verifica si las lyrics contienen el mensaje de error"""
        if not self.lyrics:
            return True
        return any("no se encontraron las letras" in line[1] for line in self.lyrics)

    def adjust_lyrics_timing(self, offset):
        """Ajusta el timing de las lyrics"""
        try:
            song_data = self.playlist[self.current_index]
            lrc_path = song_data["path"] / "lyrics.lrc"

            # Leer y modificar archivo
            with open(lrc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            modified = self._process_lines(lines, offset)

            # Escribir cambios
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.writelines(modified)

            # Recargar lyrics
            self.load_lyrics(lrc_path)

        except Exception as e:
            styled_message_box(self, "Error", f"No se pudo ajustar: {str(e)}",QMessageBox.Icon.Warning)

    def _process_lines(self, lines, offset):
        """Procesa cada línea aplicando el offset"""
        modified = []
        for i, line in enumerate(lines):
            if i == 0 or not line.strip().startswith("["):
                modified.append(line)
                continue

            # Extraer tiempo
            time_str = line[1:line.index("]")]
            try:
                new_time = self._adjust_time(time_str, offset)
                modified_line = f"[{new_time}]{line.split(']', 1)[1]}"
                modified.append(modified_line)
            except:
                modified.append(line)  # Conservar línea si hay error

        return modified

    def _adjust_time(self, time_str, offset):
        """Ajusta un timestamp por el offset"""
        minutes, rest = time_str.split(':', 1)
        seconds, milliseconds = rest.split('.', 1)

        total_seconds = (
                int(minutes) * 60 +
                int(seconds) +
                int(milliseconds) / 100 +
                offset
        )

        # Evitar tiempos negativos
        total_seconds = max(0, total_seconds)

        mins = int(total_seconds // 60)
        secs = int(total_seconds % 60)
        ms = int((total_seconds - int(total_seconds)) * 100)

        return f"{mins:02d}:{secs:02d}.{ms:02d}"


    def play_next(self):
        self.next_btn.setEnabled(False)
        self.stop_playback()
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
        else:
            self.current_index = 0
        self.play_current()
        self.next_btn.setEnabled(True)

    def play_previous(self):
        self.prev_btn.setEnabled(False)
        self.stop_playback()
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.playlist) - 1
        self.play_current()
        self.prev_btn.setEnabled(True)


    def set_volume(self, value):
        self.volume = value
        try:
            # Aplicar a todas las pistas no muteadas
            for track_name in ["drums", "vocals", "bass", "other"]:
                if not self.mute_states[track_name]:
                    self.apply_volume_to_track(track_name, self.individual_volumes[track_name])
        except Exception as e:
            pass

    def toggle_mute(self):
        try:
            sender = self.sender()
            track_name=None

            # Determinar qué botón fue presionado
            if sender == self.drums_btn:
                track_name = "drums"
            elif sender == self.vocals_btn:
                track_name = "vocals"
            elif sender == self.bass_btn:
                track_name = "bass"
            elif sender == self.other_btn:
                track_name = "other"

            if track_name:
                # Cambiar estado de mute
                self.mute_states[track_name] = not self.mute_states[track_name]

                # Cambiar icono
                icon_map = {
                    "drums": ("drums", "no_drums"),
                    "vocals": ("vocals", "no_vocals"),
                    "bass": ("bass", "no_bass"),
                    "other": ("other","no_other")
                }

                # prefix = "no_" if self.mute_states[track_name] else ""
                # icon_name = icon_map[track_name][1] if self.mute_states[track_name] else icon_map[track_name][0]
                # sender.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))

                icon_index = 1 if self.mute_states[track_name] else 0
                icon_name = icon_map[track_name][icon_index]
                sender.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))

                # Aplicar mute o volumen guardado
                if self.mute_states[track_name]:
                    self.apply_volume_to_track(track_name, 0)
                else:
                    self.apply_volume_to_track(track_name, self.individual_volumes[track_name])

        except Exception as e:
            pass

    def remove_selected(self):
        self.reset_search_indices()
        for item in self.playlist_widget.selectedItems():
            row = self.playlist_widget.row(item)
            self.playlist_widget.takeItem(row)
            del self.playlist[row]
        self.update_status()

    def update_display(self):
        if self.playback_state == "Activa" and self.current_channels:
            pos = pygame.mixer.get_busy()
            if not pos:
                self.play_next()
            else:
                current_time_ms = self.progress_song.value() + 1000
                self.progress_song.setValue(current_time_ms)

                # Actualizar el texto del progreso
                current_seconds = current_time_ms // 1000
                total_seconds = self.progress_song.maximum() // 1000

                current_mins, current_secs = divmod(current_seconds, 60)
                total_mins, total_secs = divmod(total_seconds, 60)

                self.progress_song.setFormat(
                    f"{current_mins:02d}:{current_secs:02d} / {total_mins:02d}:{total_secs:02d}"
                )

    def update_status(self):
        try:
            # Solo calcular estadísticas cada 5 segundos para no impactar rendimiento
            current_time = time.time()
            if not hasattr(self, '_last_stats_update'):
                self._last_stats_update = 0

            if current_time - self._last_stats_update > 5.0:
                cache_stats = self.get_cache_stats()
                self._cached_stats = cache_stats
                self._last_stats_update = current_time
            else:
                cache_stats = getattr(self, '_cached_stats', {'total_cached_items': 0})

            status_parts = [
                f"Canciones: {len(self.playlist)}",
                f"Reproducción: {self.playback_state.capitalize()}",
                self._format_demucs_progress(),
                # Mostrar estado de la cola
                f"En cola: {len(self.demucs_queue)}" if self.demucs_queue else "",
                f"Cache: {cache_stats.get('total_cached_items', 0)} elementos",
                f"Fecha: {datetime.now().strftime('%A - %d/%m/%Y')}",
                f"Hora: {datetime.now().strftime('%H:%M')}"
            ]

            # Filtrar partes vacías
            status_parts = [part for part in status_parts if part]

            self.status_bar.showMessage(" | ".join(status_parts))

        except Exception as e:
            print(f"❌ Error actualizando status: {e}")
            # Status de emergencia
            self.status_bar.showMessage(f"Canciones: {len(self.playlist)} | Estado: {self.playback_state}")

    def _format_demucs_progress(self):
        """Muestra progreso incluyendo estado de cola"""
        if not self.demucs_active and not self.demucs_queue:
            return ""

        if self.demucs_active:
            bars = 10
            filled = int(self.demucs_progress / 100 * bars)
            progress_bar = '■' * filled + '▢' * (bars - filled)
            return f"Separando: {progress_bar} {self.demucs_progress}%"

        if self.demucs_queue:
            return f"En cola: {len(self.demucs_queue)} trabajos"

        return ""


class DemucsWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, artist, song, use_gpu, src_path):
        super().__init__()
        self.artist = artist
        self.song = song
        self.use_gpu = use_gpu
        self.src_path = Path(src_path)
        self.base_path = Path("music_library") / artist / song
        self.process = None
        self.file_check_timer = None
        self.file_verification_attempts = 0

    # def check_cuda(self):
    #     if not TORCH_AVAILABLE:
    #         return False
    #     return torch.cuda.is_available()

    def run(self):
        try:
            # Configuración para Windows
            if os.name == 'nt':
                kwargs = {
                    'creationflags': subprocess.CREATE_NO_WINDOW,
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE
                }
            else:  # Para otros sistemas operativos
                kwargs = {
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE,
                    'start_new_session': True
                }

            # self.check_cuda()
            # Paso 1: Crear estructura de carpetas
            self.progress.emit(5)
            self.base_path.mkdir(parents=True, exist_ok=True)

            # Paso 3: Extraer portada
            self.progress.emit(15)
            self._extract_cover(self.src_path)

            # Paso 4: Generar JSON
            self.progress.emit(17)
            self._create_json()

            # Paso 5: Ejecutar Demucs con subprocess.run
            self.progress.emit(26)
            self._run_demucs_safe()

            # Paso 6: Organizar archivos generados
            self.progress.emit(83)
            self._organize_output()

            self.progress.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(f"Error: {str(e)}")

                # Usa el comando de terminal directamente
        #     cmd = [
        #         "demucs",
        #         "-n", "htdemucs_ft",
        #         "-o", str(self.base_path / "separated"),
        #         "--mp3",
        #         str(self.src_path)
        #     ]
        #
        #     # Ejecuta el comando
        #     result = subprocess.run(
        #         cmd,
        #         **kwargs,
        #         text=True,
        #         encoding='utf-8',
        #         timeout=3600,  # 1 hora máximo
        #         check=True
        #     )
        #
        #
        #     # Paso 6: Organizar archivos generados
        #     self.progress.emit(83)
        #     self._organize_output()
        #
        #     self.progress.emit(100)
        #     self.finished.emit()
        #
        #
        # except subprocess.TimeoutExpired:
        #     error_msg = "Demucs excedió el tiempo límite (1 hora)"
        #     self.error.emit(error_msg)
        # except subprocess.CalledProcessError as e:
        #     self.error.emit(f"Demucs failed with code {e.returncode}")
        # except Exception as e:
        #     self.error.emit(f"Error: {str(e)}")

    def _run_demucs_safe(self):
        """Ejecuta Demucs de manera segura con manejo de tiempo de espera"""
        try:
            # Configuración para Windows
            if os.name == 'nt':
                kwargs = {
                    'creationflags': subprocess.CREATE_NO_WINDOW,
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE
                }
            else:
                kwargs = {
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE,
                    'start_new_session': True
                }

            cmd = [
                "demucs",
                "-n", "htdemucs_ft",
                "-o", str(self.base_path / "separated"),
                "--mp3",
                str(self.src_path)
            ]

            # Ejecutar con tiempo de espera extendido
            result = subprocess.run(
                cmd,
                **kwargs,
                text=True,
                encoding='utf-8',
                timeout=7200,  # 2 horas máximo
                check=True
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("Demucs excedió el tiempo límite (2 horas)")
        except subprocess.CalledProcessError as e:
            error_msg = f"Demucs falló con código {e.returncode}"
            if e.stderr:
                error_msg += f"\nError: {e.stderr.strip()}"
            raise RuntimeError(error_msg)
        except Exception as e:
            raise RuntimeError(f"Error ejecutando Demucs: {str(e)}")

    def _verify_output_files(self, max_attempts=5, delay=2):
        """Verifica que los archivos de salida estén completos con reintentos"""
        required_files = ["drums.mp3", "vocals.mp3", "bass.mp3", "other.mp3"]
        input_stem = self.src_path.stem

        for attempt in range(max_attempts):
            try:
                # Intentar encontrar la carpeta correcta
                possible_dirs = [
                    self.base_path / "separated" / "htdemucs_ft" / input_stem,
                    self.base_path / "separated" / "htdemucs_ft" / self.song
                ]

                for demucs_dir in possible_dirs:
                    if demucs_dir.exists():
                        # Verificar todos los archivos requeridos
                        if all((demucs_dir / f).exists() for f in required_files):
                            return True

                # Si no se encontraron, esperar y reintentar
                time.sleep(delay)

            except Exception as e:
                # En caso de error de acceso, registrar y continuar
                print(f"⚠️ Error verificando archivos (intento {attempt + 1}): {str(e)}")
                time.sleep(delay)

        # Si después de todos los intentos no están los archivos
        print(f"❌ Archivos no disponibles después de {max_attempts} intentos")
        return False

    def _extract_cover(self, mp3_path):
        try:
            audio = MP3(mp3_path)
            for tag in audio.tags.values():
                if tag.FrameID == 'APIC':
                    im = Image.open(io.BytesIO(tag.data))
                    im_resized = im.resize((500, 500))
                    im_resized.save(self.base_path / "cover.png")
                    break
        except Exception as e:
            print(f"No se pudo extraer portada: {str(e)}")

    def _create_json(self):
        data = {
            self.artist: {
                self.song: {
                    "path": str(self.base_path)  # Solo guardamos la ruta
                }
            }
        }
        with open(self.base_path / "data.json", "w") as f:
            json.dump(data, f, indent=4)

    def _organize_output(self):
        input_stem = self.src_path.stem

        demucs_dir = (
                self.base_path / "separated" / "htdemucs_ft" /
                input_stem  # Nombre exacto del archivo de entrada sin extensión
        )

        if not demucs_dir.exists():
            # Fallback: intentar con solo el nombre de la canción
            demucs_dir = self.base_path / "separated" / "htdemucs_ft" / self.song
            if not demucs_dir.exists():
                raise FileNotFoundError(
                    f"No se encontró la carpeta de Demucs en: {demucs_dir}"
                )


        # Mover archivos desde la salida de Demucs
        target_dir = self.base_path / "separated"
        target_dir.mkdir(exist_ok=True)

        for stem in ["drums", "bass", "other", "vocals"]:
            src = demucs_dir / f"{stem}.mp3"
            if not src.exists():
                raise FileNotFoundError(f"Archivo no encontrado: {src}")
            shutil.move(str(src), str(target_dir / f"{stem}.mp3"))

        shutil.rmtree(demucs_dir.parent)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = AudioPlayer()
    player.show()
    sys.exit(app.exec())

