import re
import threading
from pathlib import Path
import subprocess
import json
from datetime import datetime
import time
import pygame
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QThread
from PyQt6.QtGui import QAction, QPixmap, QKeySequence, QColor, QPainter, QIcon
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QListWidget, QDockWidget, QTabWidget, QLabel, QTextEdit,
                             QPushButton, QSlider, QStatusBar, QMessageBox,
                             QProgressBar, QFrame, QListWidgetItem, QWidget)
import requests
from urllib.parse import quote
import unicodedata
from demucs_worker import DemucsWorker
from python_worker import PythonInstallWorker
from resources import styled_message_box, bg_image, resource_path
from ui_components import TitleBar, CustomDial, SizeGrip
from dialogs import AboutDialog, SearchDialog, QueueDialog, SplitDialog
from lazy_resources import LazyAudioManager, LazyImageManager, LazyLyricsManager, LazyPlaylistLoader

class AudioPlayer(QMainWindow):
    cover_loaded = pyqtSignal(QPixmap)
    lyrics_loaded = pyqtSignal(list)
    lyrics_error = pyqtSignal(str)
    lyrics_not_found = pyqtSignal()
    def __init__(self):
        super().__init__()

        # 1. Primero se cargan los managers que se usan en lazy
        self._setup_lazy_managers()

        # 2. Configuración básica de la ventana
        self._setup_window_properties()

        # 3. Inicializar variables de estado
        self._initialize_state_variables()

        # 4. Configurar audio y dependencias
        self._setup_audio_system()

        # 5. Crear y configurar la interfaz
        self._setup_user_interface()

        # 6. Configurar conexiones y eventos
        self._setup_connections()

        # 7. Inicializar timers y actualizaciones
        self._setup_timers()

        # 8. Validaciones finales
        self._perform_final_setup()

        QTimer.singleShot(200, lambda: self._delayed_start())

    def _delayed_start(self):
        """Se ejecuta después de mostrar la ventana"""
        # Cargar playlist si existe
        default_lib = Path("music_library")
        if default_lib.exists():
            self.load_folder(str(default_lib))

    def _setup_lazy_managers(self):
        """Inicializa los gestores de lazy loading"""
        self.lazy_audio = LazyAudioManager()
        self.lazy_images = LazyImageManager()
        self.lazy_lyrics = LazyLyricsManager()
        self.lazy_playlist = LazyPlaylistLoader()

    def _setup_window_properties(self):
        """Configura propiedades básicas de la ventana principal."""
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(resource_path('images/main_window/main_icon.png')))
        self.resize(1098, 813)
        self.center()

        # Configurar background y atributos de estilo
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Cargar y aplicar estilos CSS
        self._load_stylesheet()

    def _load_stylesheet(self):
        """Carga y aplica el archivo de estilos"""
        try:
            with open('estilos.css', 'r') as file:
                style = file.read()
            self.setStyleSheet(style)
        except FileNotFoundError:
            print("Warning: estilos.css not found, using default styles")

    def _initialize_state_variables(self):
        self.playlist = []
        self.current_index = -1
        self.playback_state = "Detenido"
        self.current_channels = []
        self.demucs_queue = []  # Cola de trabajos pendientes
        self.processing_multiple = False  # Indica si hay múltiples trabajos
        self.lyrics_lock = threading.Lock()
        self.python_available = False

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
        self.demucs_available = True
        self.pygame_available = True

    def _setup_audio_system(self):
        self._initialize_pygame_mixer()

        # verificación modelo Demucs y python
        self.demucs_model = None
        self.load_demucs_model()
        self._check_python_installation()

    def _initialize_pygame_mixer(self):
        """Inicializa el sistema de audio Pygame."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                pygame.mixer.set_num_channels(4)
        except pygame.error as e:
            self.pygame_available = False

    def _setup_user_interface(self):
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
        # self.menuBar().installEventFilter(self)
        self.init_status_bar()

    def _create_main_frame(self):
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
        self.title_bar = TitleBar(self)

    def _create_size_grips(self):
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
        self.tabs = QTabWidget()
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lyrics_header = QTextEdit()
        self.lyrics_header.setReadOnly(True)
        self.lyrics_header.setFixedHeight(100)
        self.lyrics_header.setObjectName("lyrics_header")

        self.lyrics_current = QTextEdit()
        self.lyrics_current.setReadOnly(True)
        self.lyrics_current.setObjectName("lyrics_current")

        self.lyrics_next = QTextEdit()
        self.lyrics_next.setReadOnly(True)
        self.lyrics_next.setFixedHeight(60)
        self.lyrics_next.setObjectName("lyrics_next")

        self.lyrics_layout = QVBoxLayout()
        self.lyrics_layout.setContentsMargins(0, 0, 0, 0)
        self.lyrics_layout.addWidget(self.lyrics_header)
        self.lyrics_layout.addWidget(self.lyrics_current)
        self.lyrics_layout.addWidget(self.lyrics_next)

        self.lyrics_container = QWidget()
        self.lyrics_container.setLayout(self.lyrics_layout)

        self.lyrics_font_size = 62
        self.tabs.addTab(self.cover_label, "Portada")
        self.tabs.addTab(self.lyrics_container, "Letras")
        self.cover_label.setPixmap(QPixmap(resource_path('images/main_window/none.png')))

    def _create_progress_bar(self):
        self.progress_song = QProgressBar(self)
        self.progress_song.setFormat("00:00 / 00:00")
        self.progress_song.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_song.setTextVisible(True)
        self.progress_song.setFixedHeight(20)
        self.progress_song.setEnabled(False)

    def _create_control_buttons(self):
        self.controls_layout = self.init_leds()

    def _create_track_controls(self):
        self.track_buttons_layout = self.track_buttons()

    def _create_playlist_dock(self):
        self.playlist_dock = QDockWidget(self)
        self.playlist_widget = QListWidget()
        self.playlist_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.playlist_widget.setFixedWidth(500)
        self.playlist_dock.setWidget(self.playlist_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.playlist_dock)

    def _setup_main_layout(self):
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
        # Conexiones de control de audio
        self._connect_playback_controls()

        # Conexiones de playlist
        self._connect_playlist_events()

        # Conexiones de dock
        self._connect_dock_events()

        # Conexiones para lazy loading
        self._connect_lazy_loading_signals()


    def _connect_lazy_loading_signals(self):
        self.lazy_playlist.playlist_updated.connect(self._on_song_loaded)
        self.lazy_playlist.loading_finished.connect(self._on_playlist_loaded)
        self.cover_loaded.connect(self._handle_cover_loaded)
        self.lyrics_loaded.connect(self._handle_lyrics_loaded)
        self.lyrics_error.connect(self._handle_lyrics_error)
        self.lyrics_not_found.connect(self._handle_lyrics_not_found)
    def _connect_playback_controls(self):
        self.play_btn.clicked.connect(self.toggle_play_pause)
        self.prev_btn.clicked.connect(self.play_previous)
        self.next_btn.clicked.connect(self.play_next)
        self.stop_btn.clicked.connect(self.stop_playback)

    def _connect_playlist_events(self):
        self.playlist_widget.itemActivated.connect(self.play_selected)

    def _connect_dock_events(self):
        self.playlist_dock.visibilityChanged.connect(self._update_playlist_menu_state)

    def _on_song_loaded(self, song_data):
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

    def _handle_lyrics_loaded(self, lyrics_data: list):
        self.lyrics = lyrics_data or []
        self.update_lyrics_menu_state()

        # 1.  Header  (siempre visible)
        song = self.playlist[self.current_index]
        self.lyrics_header.setHtml(
            f'<H1 style="color: #3AABEF;"><center>{song["artist"]}</center></H1>'
            f'<H2 style="color: #7E54AF;"><center>{song["song"]}</center></H2>'
        )

        # 2.  Limpia next
        self.lyrics_next.clear()

        # 3.  Conecta timer si no está conectado
        if not hasattr(self, 'lyrics_timer'):
            print("[DEBUG] Creando lyrics_timer")
            self.lyrics_timer = QTimer(self)
            self.lyrics_timer.timeout.connect(self.update_lyrics_display)
        self.lyrics_timer.start(100)

    def _handle_lyrics_error(self, error_msg):
        self.lyrics_current.setHtml(f'<center>Error: {error_msg}</center>')

    def _handle_lyrics_not_found(self):
        self.lyrics_current.setHtml('<center>No hay letras disponibles</center>')

    def _on_playlist_loaded(self):
        # self.status_bar.showMessage(f"Playlist cargada: {len(self.playlist)} canciones")
        self.status_label.setText(f"Playlist cargada: {len(self.playlist)} canciones")
        self.update_status()

    def _setup_timers(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def _perform_final_setup(self):
        self.update_status()

    def _setup_background(self):
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

        # Asegurar que el background esté detrás de lo demas
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
        #Redimensiona el background cuando cambia el tamaño de la ventana
        super().resizeEvent(event)
        if hasattr(self, 'background_label'):
            self.background_label.resize(self.size())

            # Volver a cargar la imagen para evitar el pixelado feo
            bg_path = resource_path('images/main_window/background.png')
            pixmap = QPixmap(bg_path)
            if not pixmap.isNull():
                self.background_label.setPixmap(pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))

    def load_demucs_model(self):
        try:
            # Verificación directa con subprocess
            result = subprocess.run(
                ['demucs', '--help'],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Demucs returned error: {result.stderr}")
            self.demucs_available = True
        except Exception as e:
            error_msg = f"Error checking Demucs: {str(e)}"
            with open("demucs_error.log", "w") as f:
                f.write(error_msg)

            self.demucs_available = False

    def _check_python_installation(self):
        """Verifica si Python está instalado ejecutando 'python --version'."""
        try:
            result = subprocess.run(
                ['python', '--version'],
                capture_output=True,
                text=True,
                shell=True,
                timeout=5
            )
            self.python_available = (result.returncode == 0)
        except Exception:
            self.python_available = False

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
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedWidth(120)
        slider.valueChanged.connect(lambda value: self.set_individual_volume(track_name, value))

    def set_individual_volume(self, track_name, value):
        # Guardar el volumen actual (antes de mute)
        self.individual_volumes[track_name] = value / 100.0

        # Si no está muteado, aplicar el volumen
        if not self.mute_states[track_name]:
            self.apply_volume_to_track(track_name, value / 100.0)

    def apply_volume_to_track(self, track_name, volume):
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
        button.setObjectName(object_name)
        button.setIconSize(QSize(120, 120))

        button._icon_path = f'images/main_window/icons01/{icon_name}.png'
        button._icon_disabled = f'images/main_window/icons01/no_{icon_name}.png'
        self._lazy_load_icon(button, False)

        button.setCheckable(True)
        button.clicked.connect(self.toggle_mute)

    def _lazy_load_icon(self, btn, muted: bool):
        path = btn._icon_disabled if muted else btn._icon_path
        icon = self.lazy_images.load_icon_cached(resource_path(path), (120, 120))
        btn.setIcon(icon)

    def install_python(self):
        if self.python_available:
            styled_message_box(
                self,
                "Python ya instalado",
                "Python ya está instalado en el sistema.",
                QMessageBox.Icon.Information
            )
            return

        # Confirmación del usuario
        reply = styled_message_box(
            self,
            "Confirmar instalación",
            "Se instalará Python 3.11.0 mediante winget.\n"
            "Esto puede tomar varios minutos y requiere permisos de administrador.\n\n"
            "¿Desea continuar?",
            QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Ejecutar en un hilo separado
        self.install_thread = QThread()
        self.install_worker = PythonInstallWorker()
        self.install_worker.moveToThread(self.install_thread)

        self.install_thread.started.connect(self.install_worker.run)
        self.install_worker.finished.connect(self._on_python_install_finished)
        self.install_worker.error.connect(self._on_python_install_error)
        self.install_worker.finished.connect(self.install_thread.quit)
        self.install_worker.finished.connect(self.install_worker.deleteLater)
        self.install_thread.finished.connect(self.install_thread.deleteLater)

        # Mostrar indicador en barra de estado
        self.status_label.setText("Instalando Python...")
        self.install_thread.start()

    def _on_python_install_finished(self):
        self.status_label.setText("Python instalado correctamente.")
        self.python_available = True
        self._update_python_menu_action()
        styled_message_box(
            self,
            "Instalación completada",
            "Python se instaló correctamente.\n"
            "Es posible que necesite reiniciar la aplicación para que los cambios surtan efecto.",
            QMessageBox.Icon.Information
        )

    def _on_python_install_error(self, error_msg):
        self.status_label.setText("Error instalando Python.")
        styled_message_box(
            self,
            "Error de instalación",
            error_msg,
            QMessageBox.Icon.Critical
        )

    def _update_python_menu_action(self):
        if hasattr(self, 'install_python_action'):
            self.install_python_action.setEnabled(not self.python_available)

    def install_demucs(self):
        styled_message_box(
            self,
            "Instalar Demucs",
            "Ejecute el siguiente comando en su terminal:\n\n"
            "pip install demucs\n\n"
            "Asegúrese de tener Python y pip instalados.",
            QMessageBox.Icon.Information
        )

    def install_CUDA(self):
        styled_message_box(
            self,
            "Instalar CUDA:",
            "Funcionalidad en Desarrollo todavía:",
            QMessageBox.Icon.Information
        )

    def add_env_vars(self):
        styled_message_box(
            self,
            "Variables de Ambiente",
            "Para agregar Python y sus scripts al PATH:\n\n"
            "1. Busque 'Variables de entorno' en Windows.\n"
            "2. En 'Variables del sistema', edite la variable 'Path'.\n"
            "3. Agregue las rutas donde instaló Python (ej. C:\\Python39 y C:\\Python39\\Scripts).\n"
            "4. Acepte los cambios y reinicie la aplicación.",
            QMessageBox.Icon.Information
        )

    def install_ytdlp(self):
        styled_message_box(
            self,
            "Instalar YT-DLP",
            "Ejecute el siguiente comando en su terminal:\n\n"
            "pip install yt-dlp\n\n"
            "Luego podrá descargar audio desde YouTube.",
            QMessageBox.Icon.Information
        )

    def download_mp3(self):
        styled_message_box(
            self,
            "Descargar MP3",
            "Funcionalidad en desarrollo.\n\n"
            "Próximamente podrá descargar audio desde YouTube directamente.",
            QMessageBox.Icon.Information
        )

    def show_about_dialog(self):
        dialog = AboutDialog(self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    def show_queue_dialog(self):
        queue_dialog = QueueDialog(self, parent=self)
        bg_image(queue_dialog, 'images/split_dialog/split.png')
        queue_dialog.exec()


    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected()

        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        # Dibujar sombra exterior
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawRoundedRect(self.rect(), 8, 8)

    # def eventFilter(self, obj, event):
    #     if obj is self.menuBar() and event.type() == QEvent.Type.Enter:
    #         print("Menú activado - barra visible:", self.status_bar.isVisible())
    #     return super().eventFilter(obj, event)

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
        split_action.setEnabled(self.demucs_available)
        if not self.demucs_available:
            split_action.setToolTip("Demucs no está instalado o no es accesible")
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
        options_menu.addAction(self.show_playlist_action)

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

        dependencias_menu = options_menu.addMenu("Dependencias")

        self.install_python_action = QAction("Instalar Python", self)
        self.install_python_action.triggered.connect(self.install_python)
        self.install_python_action.setEnabled(not self.python_available)
        dependencias_menu.addAction(self.install_python_action)

        install_demucs_action = QAction("Instalar Demucs", self)
        install_demucs_action.triggered.connect(self.install_demucs)
        dependencias_menu.addAction(install_demucs_action)

        install_CUDA_action = QAction("Instalar CUDA (chip Nvidia)", self)
        install_CUDA_action.triggered.connect(self.install_CUDA)
        dependencias_menu.addAction(install_CUDA_action)

        add_env_vars_action = QAction("Agregar Variables de Ambiente", self)
        add_env_vars_action.triggered.connect(self.add_env_vars)
        dependencias_menu.addAction(add_env_vars_action)

        install_ytdlp_action = QAction("Instalar YT-DLP (Youtube -> MP3)", self)
        install_ytdlp_action.triggered.connect(self.install_ytdlp)
        dependencias_menu.addAction(install_ytdlp_action)

        # Separador opcional
        options_menu.addSeparator()

        download_mp3_action = QAction("Descargar MP3...", self)
        download_mp3_action.triggered.connect(self.download_mp3)
        options_menu.addAction(download_mp3_action)

        about_action = QAction("Sobre Playit", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        queue_action = QAction("Mostrar Queue", self)
        queue_action.triggered.connect(self.show_queue_dialog)
        help_menu.addAction(queue_action)

        # Inicialmente deshabilitadas
        self.advance_action.setEnabled(False)
        self.delay_action.setEnabled(False)


    def increase_lyrics_font(self):
        self.lyrics_font_size += 2
        if self.lyrics_font_size > 82:  # Límite máximo
            self.lyrics_font_size = 20
        self.apply_lyrics_font()

    def decrease_lyrics_font(self):
        self.lyrics_font_size -= 2
        if self.lyrics_font_size < 20:  # Límite mínimo
            self.lyrics_font_size = 82
        self.apply_lyrics_font()

    def apply_lyrics_font(self):
        self.lyrics_current.setStyleSheet(f"""
                                    QTextEdit {{
                                        font-size: {self.lyrics_font_size}px;                                
                                    }}
                                """)
    def _toggle_playlist_visibility(self, state):
        self.playlist_dock.setVisible(state)

    def _update_playlist_menu_state(self, visible):
        self.show_playlist_action.setChecked(visible)

    def closeEvent(self, event):
        if self.playlist_dock.isVisible():
            self.playlist_dock.close()
        super().closeEvent(event)

    def show_search_dialog(self):
        dialog = SearchDialog(self)

        bg_image(dialog,'images/split_dialog/split.png')
        dialog.search_requested.connect(self.handle_search)
        dialog.exec()

    def handle_search(self, search_text):
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

    def show_split_dialog(self):
        if not self.demucs_available:
            styled_message_box(
                self,
                "Funcionalidad no disponible",
                "La separación de pistas requiere Demucs, pero no está instalado o no es accesible.\n\n"
                "Puede instalar Demucs con: pip install demucs",
                QMessageBox.Icon.Warning
            )
            return

        self.split_dialog = SplitDialog(self)
        bg_image(self.split_dialog, 'images/split_dialog/split.png')
        self.split_dialog.process_started.connect(self.process_song)
        # Conectar al método existente
        self.split_dialog.show()

    def process_song(self, artist, song, file_path):
        # Crear objeto de trabajo
        job = {
            'artist': artist,
            'song': song,
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
        if not self.demucs_queue:
            self.demucs_active = False
            self.processing_multiple = False
            self.update_status()
            return

        # Obtener el próximo trabajo
        job = self.demucs_queue.pop(0)
        self._start_demucs_job(job)

    def _start_demucs_job(self, job):
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

    def check_files(self):
        """
        Verifica que TODOS los archivos de audio separados existan.
        Incluye contador de reintentos para evitar bucles infinitos.
        """
        # Inicializar contador si no existe
        if not hasattr(self, '_verification_attempts'):
            self._verification_attempts = 0

        # Límite máximo de intentos (60 intentos = 30 minutos con timer de 30 seg)
        MAX_ATTEMPTS = 60

        if self._verification_attempts >= MAX_ATTEMPTS:
            self.verification_timer.stop()
            self._verification_attempts = 0
            styled_message_box(
                self,
                "Timeout",
                f"No se pudieron verificar todos los archivos de:\n"
                f"{self.last_in_queue['artist']} - {self.last_in_queue['song']}\n\n"
                f"Verifique manualmente la carpeta separated/",
                QMessageBox.Icon.Warning
            )
            return

        # Validar datos
        if not self.last_in_queue.get('artist') or not self.last_in_queue.get('song'):
            self.verification_timer.stop()
            self._verification_attempts = 0
            return

        # Construir ruta
        base_path = Path(f"music_library/{self.last_in_queue['artist']}/{self.last_in_queue['song']}/separated")

        if not base_path.exists():
            self._verification_attempts += 1
            return

        # Archivos requeridos
        required_files = ['drums.mp3', 'vocals.mp3', 'bass.mp3', 'other.mp3']

        # Verificar cada archivo
        all_present = True
        for archivo in required_files:
            if not (base_path / archivo).exists():
                all_present = False
                break

        if all_present:
            # ✅ Todos presentes
            self.verification_timer.stop()
            self._verification_attempts = 0
            self.scan_folder(Path("music_library"))
            print(f"✅ Verificación completa: {self.last_in_queue['artist']} - {self.last_in_queue['song']}")
        else:
            # ⏳ Faltan archivos, incrementar contador
            self._verification_attempts += 1
            print(f"⏳ Intento {self._verification_attempts}/{MAX_ATTEMPTS} - Esperando archivos completos...")

    def _cleanup_current_job(self):
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
        # Primero limpiar el trabajo actual
        self._cleanup_current_job()

        # Mostrar error solo si es el único trabajo
        if not self.processing_multiple:
            styled_message_box(self, "Error", error_msg, QMessageBox.Icon.Critical)

        # Continuar con el siguiente trabajo
        self._process_next_job()


    def _update_demucs_progress(self, value):
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
        QApplication.instance().quit()


    def init_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Crear QLabel permanente (siempre visible)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Añadirlo como widget permanente
        self.status_bar.addPermanentWidget(self.status_label, stretch=1)

        # Mensaje temporal opcional (se borrará después de 3 segundos)
        self.status_bar.showMessage("Listo", 3000)

        self.update_status()

    def load_folder(self, path: str = None):
        from PyQt6.QtWidgets import QFileDialog
        from os.path import expanduser
        from pathlib import Path

        if not path:
            path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", expanduser("~/Music"))
        if path:
            # Limpiar playlist actual primero
            self.clear_playlist()

            # Mostrar indicador de carga
            self.status_label.setText("Cargando playlist...")

            # Usar lazy loading para cargar la carpeta
            try:
                self.lazy_playlist.load_playlist_lazy(Path(path))
            except Exception as e:
                styled_message_box(self, "Error", f"Error iniciando carga: {str(e)}", QMessageBox.Icon.Critical)
                self.status_label.setText("Error cargando playlist")

    def reset_search_indices(self):
        self.search_results = []
        self.search_index = 0
        self.current_search = ""

    def clear_playlist(self):
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
        normalized = unicodedata.normalize('NFKD', text.lower())
        return ''.join([c for c in normalized if not unicodedata.combining(c)])

    def _fetch_lyrics_from_api(self, artist, song, output_dir):
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
            self._write_lyrics_file(output_dir, artist, song, None)


    def _write_lyrics_file(self, output_dir, artist, song, lyrics):
        title_line = ''

        if not lyrics:
            # Caso sin letras
            content = '[00:00.00]<center style="color: #ff2626;">Letras no encontradas</center>\n'
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
                        processed_line = f'{timestamp}]<center>{text.strip()}</center>'
                        processed_lines.append(processed_line)

            # Unir el contenido
            content = title_line + '\n'.join(processed_lines) + '\n'

        # Escribir el archivo
        with open(output_dir / "lyrics.lrc", "w", encoding="utf-8") as f:
            f.write(content)

    def play_selected(self):
        # self.stop_playback()
        self.current_index = self.playlist_widget.currentRow()
        self.play_current()

    def _control_channels(self, action: str):
        """Control centralizado para operaciones en los canales de audio.
        Acciones soportadas: 'play', 'stop', 'pause', 'unpause'
        """
        if not self.current_channels:
            return

        for channel in self.current_channels:
            if action == 'play':
                channel.unpause()
            elif action == 'stop':
                channel.stop()
            elif action == 'pause':
                channel.pause()
            elif action == 'unpause':
                channel.unpause()

    def _setup_audio(self) -> bool:
        """Método para usar lazy loading de audio"""
        if not (0 <= self.current_index < len(self.playlist)):
            return False

        song = self.playlist[self.current_index]
        path = Path(song["path"])

        try:
            # Usar lazy loading para cargar los sonidos
            sounds = self.lazy_audio.load_audio_lazy(path)

            if not sounds:
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

            # Crear canales de reproducción
            self.current_channels = []
            for i, sound in enumerate(sounds):
                try:
                    channel = sound.play()
                    channel.pause()  # Pausar inmediatamente para control manual
                    self.current_channels.append(channel)
                except Exception as e:
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
            except Exception as e:
                print(f"⚠️ Error configurando progreso: {e}")

            return True

        except Exception as e:
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
        # Detener reproducción actual
        self.stop_playback()

        if not (0 <= self.current_index < len(self.playlist)):
            return

        # Configurar audio
        if not self._setup_audio():
            return

        # Restaurar estados de mute
        self._restore_mute_states()

        # Actualizar metadatos (portada, letras, etc.)
        self._update_metadata()

        # Actualizar UI
        self._update_playback_ui('Activa')
        self.playback_state = "Activa"

        # Aplicar volumen
        self.set_volume(self.volume)

        # Actualizar menú de letras
        self.update_lyrics_menu_state()

        # Actualizar resaltado en playlist
        self.highlight_current_song()

        # Iniciar reproducción
        self._control_channels('play')

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
        self.lyrics = []
        self._last_progress_seconds = -1
        self.update_lyrics_menu_state()
        self.lyrics_header.clear()
        self.lyrics_current.clear()
        self.lyrics_next.clear()

        # Quitar resaltado de la canción actual
        self.clear_song_highlight()

    def highlight_current_song(self):
        # Primero quitar cualquier resaltado existente
        self.clear_song_highlight()

        # Resaltar el ítem actual si es válido
        if 0 <= self.current_index < self.playlist_widget.count():
            item = self.playlist_widget.item(self.current_index)

            # Crear fuente cursiva
            font = item.font()
            font.setItalic(True)
            item.setFont(font)

            # Establecer color de texto
            item.setForeground(QColor("black"))
            item.setBackground(QColor("#eea1cd"))

            # Seleccionar y hacer scroll al ítem
            self.playlist_widget.setCurrentItem(item)

    def clear_song_highlight(self):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)

            # Restaurar fuente normal
            font = item.font()
            font.setItalic(False)
            item.setFont(font)

            # Restaurar color de texto por defecto
            item.setForeground(QColor("white"))
            item.setBackground(QColor("transparent"))

    def _update_metadata(self):
        try:
            self.lyrics_header.clear()
            self.lyrics_current.clear()
            self.lyrics_next.clear()

            song = self.playlist[self.current_index]
            path = Path(song["path"])
            lrc_path = path / "lyrics.lrc"

            # Actualizar título de ventana
            title = f"{song['artist']} - {song['song']}"
            self.title_bar.title.setText(title)

            # Cargar portada usando lazy loading (async)
            def load_cover_async():
                try:
                    cover_pixmap = self.lazy_images.load_cover_lazy(path, (500, 500))
                    self.cover_loaded.emit(cover_pixmap)
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
                    self.lyrics_error.emit(str(e))

            #  Ejecutar carga asíncrona
            threading.Thread(target=load_cover_async, daemon=True).start()
            threading.Thread(target=load_lyrics_async, daemon=True).start()

            # Precargar recursos de las siguientes canciones
            self._preload_adjacent_resources()

        except Exception as e:
            print(f"❌ Error actualizando metadatos: {e}")

    def get_cache_stats(self) -> dict:
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
            return {
                "error": str(e),
                "total_cached_items": 0,
                "overall_hit_rate": 0,
                "memory_utilization": {"audio": 0, "images": 0, "lyrics": 0}
            }

    def _preload_adjacent_resources(self):
        if not self.playlist:
            return

        def preload_worker():
            try:
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
                    except Exception as e:
                        print(f"❌ Error precargando portada {offset}: {e}")

            except Exception as e:
                print(f"❌ Error en precarga general: {e}")

        # Ejecutar en hilo separado para no bloquear
        threading.Thread(target=preload_worker, daemon=True).start()

    def cleanup_resources_manual(self):
        try:
            # Obtener estadísticas antes
            before_stats = self.get_cache_stats()

            # Limpiar caches
            self.lazy_audio.cache.clear()
            self.lazy_images.cache.clear()
            self.lazy_lyrics.cache.clear()

            # Obtener estadísticas después
            after_stats = self.get_cache_stats()

            # Mostrar mensaje al usuario
            styled_message_box(
                self,
                "Limpieza Completa",
                f"Cache limpiado exitosamente.\n"
                f"Elementos eliminados: {before_stats['total_cached_items'] - after_stats['total_cached_items']}\n"
                f"Memoria liberada aproximada: {(before_stats['total_cached_items'] - after_stats['total_cached_items']) * 2:.1f}MB"
            )

        except Exception as e:
            styled_message_box(
                self,
                "Error",
                f"Error durante la limpieza: {str(e)}",
                QMessageBox.Icon.Warning
            )
        self.update_status()

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
        if not self.lyrics or self.playback_state != "Activa":
            return

        current_time = self.progress_song.value() / 1000.0

        current_html = ""
        next_html = ""
        for i, (t, html) in enumerate(self.lyrics):
            if current_time >= t:
                current_html = html
                if i + 1 < len(self.lyrics):
                    next_html = self.lyrics[i + 1][1]
                else:
                    next_html = ""
            else:
                break

        if getattr(self, "_last_current_html", None) != current_html:
            self._last_current_html = current_html


        self.lyrics_current.setHtml(current_html)
        self.lyrics_next.setHtml(f'<center>{next_html}</center>')

    def update_lyrics_menu_state(self):
        enabled = (
                self.playback_state == "Activa" and
                self.current_index != -1 and
                not self._lyrics_has_error()
        )
        self.advance_action.setEnabled(enabled)
        self.delay_action.setEnabled(enabled)

    def _lyrics_has_error(self):
        if not self.lyrics or not isinstance(self.lyrics, list):
            return True
        for _, html in self.lyrics:
            text = html.lower()
            if "no se encontraron" in text or "letras no encontradas" in text:
                return True
        return False

    def adjust_lyrics_timing(self, offset):
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
        # Early return para evitar procesamiento innecesario
        if self.playback_state != "Activa" or not self.current_channels:
            return

        try:
            # Verificar si el mixer sigue ocupado
            if not pygame.mixer.get_busy():
                # La canción terminó naturalmente, pasar a la siguiente
                self.play_next()
                return

            # Actualizar progreso solo si hay cambios significativos
            current_time_ms = self.progress_song.value() + 1000

            # Verificar límites para evitar desbordamiento
            if current_time_ms <= self.progress_song.maximum():
                self.progress_song.setValue(current_time_ms)

                # Actualizar el texto del progreso de forma más eficiente
                current_seconds = current_time_ms // 1000
                total_seconds = self.progress_song.maximum() // 1000

                # Inicializar el atributo si no existe
                if not hasattr(self, '_last_progress_seconds'):
                    self._last_progress_seconds = -1

                # Evitar recálculos innecesarios si los valores no cambiaron
                if self._last_progress_seconds == current_seconds:
                    return

                self._last_progress_seconds = current_seconds

                current_mins, current_secs = divmod(current_seconds, 60)
                total_mins, total_secs = divmod(total_seconds, 60)

                self.progress_song.setFormat(
                    f"{current_mins:02d}:{current_secs:02d} / {total_mins:02d}:{total_secs:02d}"
                )
            else:
                # Si se excedió el máximo, terminar la canción
                self.play_next()

        except pygame.error as e:
            # Manejar errores del mixer de forma elegante
            print(f"Error en mixer durante actualización: {e}")
            self.stop_playback()
        except Exception as e:
            # Manejar cualquier otro error inesperado
            print(f"Error inesperado en update_display: {e}")
            self.stop_playback()

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

            self.status_label.setText(" | ".join(status_parts))


        except Exception as e:
            # Status de emergencia
            self.status_label.setText(f"Canciones: {len(self.playlist)} | Estado: {self.playback_state}")

    def _format_demucs_progress(self):
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

