import re
import threading
from pathlib import Path
import json
from datetime import datetime
import time
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QThread
from PyQt6.QtGui import QAction, QPixmap, QKeySequence, QColor, QPainter, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QListWidget, QDockWidget, QTabWidget, QLabel, QTextEdit,
    QPushButton, QSlider, QStatusBar, QMessageBox,
    QFrame, QListWidgetItem, QWidget, QFileDialog,
)
import requests
from urllib.parse import quote
import unicodedata
import sounddevice as sd
import soundfile as sf
import numpy as np

# Módulos propios
from platform_utils import (
    IS_WINDOWS, IS_LINUX,
    run_silent, check_command_exists, get_python_cmd,
    detect_nvidia_gpu, check_visual_cpp, check_pytorch_cuda,
)
from demucs_worker import DemucsWorker
from python_worker import PythonInstallWorker
from visualc_worker import VisualCWorker
from ytdlp_worker import YTDLPWorker
from ffmpeg_worker import FFmpegWorker
from cuda_worker import CudaInstallWorker
from ytdlp_download_worker import YTDLPDownloadWorker
from demucs_install_worker import DemucsInstallWorker
from resources import styled_message_box, bg_image, resource_path
from ui_components import TitleBar, CustomDial, SizeGrip
from dialogs import AboutDialog, QueueDialog, SplitDialog, DownloadDialog
from lazy_resources import LazyAudioManager, LazyImageManager, LazyLyricsManager, LazyPlaylistLoader

# ──────────────────────────────────────────────────────────────────────────────
# ── Constantes ────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
TRACK_NAMES = ("drums", "vocals", "bass", "other")
DEFAULT_LIBRARY = Path("music_library")
DEFAULT_VOLUME = 25
LYRICS_FONT_MIN = 20
LYRICS_FONT_MAX = 82
LYRICS_FONT_DEFAULT = 62
STATUS_CACHE_TTL = 5.0
VERIFICATION_MAX_ATTEMPTS = 60
VERIFICATION_INTERVAL_MS = 30_000


class AudioPlayer(QMainWindow):
    """Ventana principal — el director de orquesta."""

    cover_loaded = pyqtSignal(QPixmap)
    lyrics_loaded = pyqtSignal(list)
    lyrics_error = pyqtSignal(str)
    lyrics_not_found = pyqtSignal()

    # ──────────────────────────────────────────────────────────────────────
    # ── Inicialización ───────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self._setup_lazy_managers()
        self._setup_window_properties()
        self._initialize_state_variables()
        self._setup_audio_system()
        self._setup_user_interface()
        self._setup_connections()
        self._setup_timers()
        self._perform_final_setup()
        QTimer.singleShot(200, self._delayed_start)

    def _delayed_start(self):
        if DEFAULT_LIBRARY.exists():
            self.load_folder(str(DEFAULT_LIBRARY))

    def _setup_lazy_managers(self):
        self.lazy_audio = LazyAudioManager()
        self.lazy_images = LazyImageManager()
        self.lazy_lyrics = LazyLyricsManager()
        self.lazy_playlist = LazyPlaylistLoader()

    def _setup_window_properties(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(QIcon(resource_path('images/main_window/main_icon.png')))
        self.resize(1098, 813)
        self.center()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._load_stylesheet()

    def _load_stylesheet(self):
        try:
            with open('estilos.css', 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            styled_message_box(
                self, "Error de estilos",
                "Archivo de estilos no encontrado",
                QMessageBox.Icon.Critical,
            )

    def _initialize_state_variables(self):
        # Playlist
        self.playlist: list[dict] = []
        self.current_index = -1
        self.playback_state = "Detenido"
        self.current_channels: list = []

        # Cola Demucs
        self.demucs_queue: list[dict] = []
        self.demucs_active = False
        self.demucs_progress = 0
        self.processing = False
        self.processing_multiple = False
        self.demucs_thread = None
        self.demucs_worker = None
        self.last_in_queue = {"artist": "", "song": ""}
        self._verification_attempts = 0

        # Dependencias — marcamos vc_available=True en Linux (no se necesita)
        self.python_available = False
        self.vc_available = not IS_WINDOWS  # Linux no necesita Visual C++
        self.ytdlp_available = False
        self.ffmpeg_available = False
        self.gpu_available = False
        self.pytorch_cuda_available = False
        self.demucs_available = True
        self.demucs_install_in_progress = False
        self.cuda_install_in_progress = False

        # Audio / volumen
        self.volume = DEFAULT_VOLUME
        self.individual_volumes = {t: 1.0 for t in TRACK_NAMES}
        self.mute_states = {t: False for t in TRACK_NAMES}
        self._seeking = False
        self._sd_streams: list = []
        self._track_data: list = []
        self._seek_position = 0
        self._stream_lock = threading.Lock()
        self._stream_cancel_flags: list = []
        self._stream_pause_flag = threading.Event()
        self._stream_pause_flag.set()

        # Letras
        self.lyrics: list = []
        self.lyrics_lock = threading.Lock()
        self.lyrics_font_size = LYRICS_FONT_DEFAULT
        self._last_current_html = None
        self._last_progress_seconds = -1

        # Diálogos
        self.split_dialog = None

        # Caché de status
        self._last_stats_update = 0.0
        self._cached_stats: dict = {"total_cached_items": 0}

    def _setup_audio_system(self):
        """
        Verifica dependencias del sistema.

        Analogía: Antes de abrir el restaurante, verificamos que
        tengamos gas, agua, electricidad y los utensilios.
        """
        self.demucs_model = None
        self.load_demucs_model()
        self._check_python_installation()
        self._check_ffmpeg_installation()
        if IS_WINDOWS:
            self._check_vc_installation()
        self._check_ytdlp_installation()
        self._check_gpu()
        self._check_pytorch_cuda()

    # ──────────────────────────────────────────────────────────────────────
    # ── UI ───────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _setup_user_interface(self):
        self._create_main_frame()
        self._setup_background()
        self._create_title_bar()
        self._create_size_grips()
        self._create_tab_widget()
        self._create_progress_bar()
        self._create_control_buttons()
        self._create_track_controls()
        self._create_playlist_dock()
        self._setup_main_layout()
        self.init_menu()
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
        positions = ("top", "bottom", "left", "right",
                     "top_left", "top_right", "bottom_left", "bottom_right")
        self.size_grips = {pos: SizeGrip(self, pos) for pos in positions}

    def _create_tab_widget(self):
        self.tabs = QTabWidget()

        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setPixmap(QPixmap(resource_path('images/main_window/none.png')))

        self.lyrics_header = QTextEdit()
        self.lyrics_header.setReadOnly(True)
        self.lyrics_header.setFixedHeight(100)
        self.lyrics_header.setObjectName("lyrics_header")

        self.lyrics_current = QTextEdit()
        self.lyrics_current.setReadOnly(True)
        self.lyrics_current.setObjectName("lyrics_current")
        self.lyrics_current.setStyleSheet("background: transparent; border: none;")

        self.lyrics_next = QTextEdit()
        self.lyrics_next.setReadOnly(True)
        self.lyrics_next.setFixedHeight(60)
        self.lyrics_next.setObjectName("lyrics_next")
        self.lyrics_next.setStyleSheet("background: transparent; border: none;")

        lyrics_layout = QVBoxLayout()
        lyrics_layout.setContentsMargins(0, 0, 0, 0)
        for w in (self.lyrics_header, self.lyrics_current, self.lyrics_next):
            lyrics_layout.addWidget(w)

        self.lyrics_container = QWidget()
        self.lyrics_container.setLayout(lyrics_layout)

        self.tabs.addTab(self.cover_label, "Portada")
        self.tabs.addTab(self.lyrics_container, "Letras")

    def _create_progress_bar(self):
        self.progress_song = QSlider(Qt.Orientation.Horizontal, self)
        self.progress_song.setFixedHeight(20)
        self.progress_song.setEnabled(False)
        self.progress_song.setRange(0, 0)
        self.progress_song.setValue(0)
        self.progress_song.setObjectName("progressbar")

        self.progress_label = QLabel("00:00 / 00:00", self)
        self.progress_label.setObjectName("progresslabel")
        self.progress_label.setStyleSheet("background: transparent; border: none;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

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
        layout.addWidget(self.title_bar)
        layout.addWidget(self.tabs)
        layout.addLayout(self.track_buttons_layout)
        layout.addSpacing(4)
        layout.addWidget(self.progress_label)
        layout.addSpacing(4)
        layout.addWidget(self.progress_song)
        layout.addLayout(self.controls_layout)

    def _setup_background(self):
        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        self.background_label.setScaledContents(True)
        self._apply_background_pixmap()
        self.background_label.lower()
        self.main_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)

    def _apply_background_pixmap(self):
        pixmap = QPixmap(resource_path('images/main_window/background.png'))
        if not pixmap.isNull():
            self.background_label.setPixmap(pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    # ──────────────────────────────────────────────────────────────────────
    # ── Conexiones ───────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _setup_connections(self):
        self._connect_playback_controls()
        self._connect_playlist_events()
        self._connect_dock_events()
        self._connect_lazy_loading_signals()

    def _connect_playback_controls(self):
        self.play_btn.clicked.connect(self.toggle_play_pause)
        self.prev_btn.clicked.connect(self.play_previous)
        self.next_btn.clicked.connect(self.play_next)
        self.stop_btn.clicked.connect(self.stop_playback)
        self.progress_song.sliderReleased.connect(self._on_progress_released)
        self.progress_song.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _connect_playlist_events(self):
        self.playlist_widget.itemActivated.connect(self.play_selected)

    def _connect_dock_events(self):
        self.playlist_dock.visibilityChanged.connect(self._update_playlist_menu_state)

    def _connect_lazy_loading_signals(self):
        self.lazy_playlist.playlist_updated.connect(self._on_song_loaded)
        self.lazy_playlist.loading_finished.connect(self._on_playlist_loaded)
        self.cover_loaded.connect(self._handle_cover_loaded)
        self.lyrics_loaded.connect(self._handle_lyrics_loaded)
        self.lyrics_error.connect(self._handle_lyrics_error)
        self.lyrics_not_found.connect(self._handle_lyrics_not_found)

    # ──────────────────────────────────────────────────────────────────────
    # ── Timers ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _setup_timers(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.timer.start(1000)

    def _perform_final_setup(self):
        self.update_status()

    # ──────────────────────────────────────────────────────────────────────
    # ── Eventos de ventana ───────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'background_label'):
            self.background_label.resize(self.size())
            self._apply_background_pixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawRoundedRect(self.rect(), 8, 8)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Right:
            new_val = min(self.progress_song.value() + 5000, self.progress_song.maximum())
            self.seek_to(new_val)
        elif key == Qt.Key.Key_Left:
            new_val = max(self.progress_song.value() - 5000, 0)
            self.seek_to(new_val)
        elif key == Qt.Key.Key_Delete:
            self.remove_selected()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.playlist_dock.isVisible():
            self.playlist_dock.close()
        super().closeEvent(event)

    def center(self):
        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

    # ──────────────────────────────────────────────────────────────────────
    # ── Lazy loading callbacks ───────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _on_song_loaded(self, song_data: dict):
        if any(t['artist'] == song_data['artist'] and t['song'] == song_data['song']
               for t in self.playlist):
            return

        self.playlist.append(song_data)
        item = QListWidgetItem(f"{song_data['artist']} - {song_data['song']}")
        item.setIcon(QIcon(resource_path('images/main_window/audio_icon.png')))
        self.playlist_widget.addItem(item)

        if len(self.playlist) == 1:
            self._set_playback_buttons_enabled(True)

        self._check_and_fetch_lyrics_async(
            song_data['path'], song_data['artist'], song_data['song']
        )

    def _on_playlist_loaded(self):
        self.status_label.setText(f"Playlist cargada: {len(self.playlist)} canciones")
        self.update_status()

    def _handle_cover_loaded(self, pixmap: QPixmap):
        self.cover_label.setPixmap(pixmap)

    def _handle_lyrics_loaded(self, lyrics_data: list):
        self.lyrics = lyrics_data or []
        self.update_lyrics_menu_state()

        song = self.playlist[self.current_index]
        self.lyrics_header.setHtml(
            f'<H1 style="color: #3AABEF;"><center>{song["artist"]}</center></H1>'
            f'<H2 style="color: #7E54AF;"><center>{song["song"]}</center></H2>'
        )
        self.lyrics_next.clear()

        if not hasattr(self, 'lyrics_timer'):
            self.lyrics_timer = QTimer(self)
            self.lyrics_timer.timeout.connect(self.update_lyrics_display)
        self.lyrics_timer.start(100)

    def _handle_lyrics_error(self, error_msg: str):
        self.lyrics_current.setHtml(f'<center>Error: {error_msg}</center>')

    def _handle_lyrics_not_found(self):
        self.lyrics_current.setHtml('<center>No hay letras disponibles</center>')

    # ──────────────────────────────────────────────────────────────────────
    # ── Controles de reproducción ────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def play_current(self):
        self.stop_playback()
        if not (0 <= self.current_index < len(self.playlist)):
            return
        if not self._setup_audio():
            return
        self._restore_mute_states()
        self._update_metadata()
        self._update_playback_ui('Activa')
        self.set_volume(self.volume)
        self.update_lyrics_menu_state()
        self.highlight_current_song()
        self._control_channels('play')

    def play_next(self):
        self.next_btn.setEnabled(False)
        self.stop_playback()
        self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_current()
        self.next_btn.setEnabled(True)

    def play_previous(self):
        self.prev_btn.setEnabled(False)
        self.stop_playback()
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_current()
        self.prev_btn.setEnabled(True)

    def play_selected(self):
        self.current_index = self.playlist_widget.currentRow()
        self.play_current()

    def toggle_play_pause(self):
        if self.playback_state == "Activa":
            self._control_channels('pause')
            self._update_playback_ui('Pausada')
        else:
            self._control_channels('unpause')
            self._update_playback_ui('Activa')
        self.update_lyrics_menu_state()

    def stop_playback(self):
        """
        Detiene la reproducción.

        MEJORA: Eliminado el time.sleep(0.1) que bloqueaba el hilo principal.
        El stream_lock ya se encarga de la sincronización.
        """
        self._control_channels('stop')
        self._update_playback_ui('Detenido')
        self.cover_label.setPixmap(QPixmap(resource_path('images/main_window/none.png')))
        self.progress_song.setValue(0)
        self.current_channels = []
        self.lyrics = []
        self._last_progress_seconds = -1
        self.update_lyrics_menu_state()
        for w in (self.lyrics_header, self.lyrics_current, self.lyrics_next):
            w.clear()
        self.clear_song_highlight()

    def _control_channels(self, action: str):
        with self._stream_lock:
            if action == 'stop':
                self._stream_pause_flag.set()
                self._stop_streams()
                self._seek_position = 0
            elif action == 'pause':
                self._stream_pause_flag.clear()
            elif action in ('play', 'unpause'):
                if not self._sd_streams:
                    self._start_streams(self._seek_position)
                else:
                    self._stream_pause_flag.set()

    def _stop_streams(self):
        for flag in self._stream_cancel_flags:
            flag.set()
        self._stream_cancel_flags = []

        for stream in self._sd_streams:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._sd_streams = []

    def _start_streams(self, start_frame: int = 0):
        self._stop_streams()
        if not self._track_data:
            return

        self._seek_position = start_frame
        sr = self._track_data[0][1]
        channels = self._track_data[0][0].shape[1]

        cancel_flag = threading.Event()
        self._stream_cancel_flags = [cancel_flag]

        stream = sd.OutputStream(samplerate=sr, channels=channels, dtype='float32')
        stream.start()
        self._sd_streams = [stream]

        t = threading.Thread(
            target=self._stream_writer,
            args=(stream, start_frame, cancel_flag),
            daemon=True,
        )
        t.start()

    def _stream_writer(self, stream, start_frame, cancel_flag):
        """
        Escribe audio mezclado al stream.

        Analogía: Es como un DJ en tiempo real que mezcla 4 canales
        (drums, vocals, bass, other), ajustando el volumen de cada
        uno y enviando la mezcla final a los altavoces.
        """
        chunk_size = 1024
        pos = start_frame

        while pos < len(self._track_data[0][0]):
            if cancel_flag.is_set():
                break
            self._stream_pause_flag.wait()
            if cancel_flag.is_set():
                break

            end = min(pos + chunk_size, len(self._track_data[0][0]))
            chunk = np.zeros(
                (end - pos, self._track_data[0][0].shape[1]),
                dtype='float32',
            )

            for i, (track_data, _) in enumerate(self._track_data):
                track = TRACK_NAMES[i]
                vol = 0.0 if self.mute_states[track] else (
                    self.individual_volumes[track] * (self.volume / 100.0)
                )
                chunk += track_data[pos:end] * vol

            peak = np.max(np.abs(chunk))
            if peak > 1.0:
                chunk /= peak

            try:
                stream.write(chunk)
            except Exception:
                break

            pos = end
            self._seek_position = pos

        # Fin natural de canción
        if not cancel_flag.is_set():
            QTimer.singleShot(0, self.play_next)

    def seek_to(self, target_ms: int):
        if self._seeking or not self._track_data:
            return
        self._seeking = True
        try:
            max_ms = self.progress_song.maximum()
            target_ms = max(0, min(target_ms, max_ms - 1000))

            if target_ms >= max_ms - 1000:
                self._seeking = False
                self.play_next()
                return

            sr = self._track_data[0][1]
            target_frame = int((target_ms / 1000.0) * sr)
            was_playing = self.playback_state == "Activa"

            self._stop_streams()

            if was_playing:
                self._start_streams(target_frame)

            self._seek_position = target_frame
            self.progress_song.setValue(target_ms)
            self._last_progress_seconds = target_ms // 1000
            self.update_lyrics_display()
        finally:
            self._seeking = False

    def _on_progress_released(self):
        self.seek_to(self.progress_song.value())
        self.update_lyrics_display()

    def _setup_audio(self) -> bool:
        if not (0 <= self.current_index < len(self.playlist)):
            return False

        song = self.playlist[self.current_index]
        path = Path(song["path"])

        try:
            track_paths = self.lazy_audio.load_audio_lazy(path)
            if not track_paths:
                styled_message_box(
                    self, "Error de Audio",
                    f"No se encontraron las pistas separadas para:\n"
                    f"{song['artist']} - {song['song']}",
                    QMessageBox.Icon.Warning,
                )
                return False

            self._track_data = []
            for track_path in track_paths:
                data, sr = sf.read(str(track_path), dtype='float32', always_2d=True)
                self._track_data.append((data, sr))

            self._seek_position = 0
            self._stop_streams()

            length_s = len(self._track_data[0][0]) / self._track_data[0][1]
            length_ms = int(length_s * 1000)
            total_m, total_s = divmod(int(length_s), 60)
            self.progress_song.setRange(0, length_ms)
            self.progress_song.setValue(0)
            self.progress_label.setText(f"00:00 / {total_m:02d}:{total_s:02d}")
            return True

        except Exception as e:
            styled_message_box(
                self, "Error", f"Error cargando audio: {str(e)}",
                QMessageBox.Icon.Critical,
            )
            return False

    # ──────────────────────────────────────────────────────────────────────
    # ── UI de reproducción ───────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _update_playback_ui(self, state: str):
        self.playback_state = state
        stopped = state == "Detenido"
        self.stop_btn.setEnabled(not stopped)
        self.progress_song.setEnabled(not stopped)
        for btn in (self.drums_btn, self.vocals_btn, self.bass_btn, self.other_btn):
            btn.setEnabled(True)
        self.update_status()

    def _restore_mute_states(self):
        btns = {
            "drums": self.drums_btn, "vocals": self.vocals_btn,
            "bass": self.bass_btn, "other": self.other_btn,
        }
        for track, btn in btns.items():
            icon_name = f"no_{track}" if self.mute_states[track] else track
            btn.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))
            btn.setChecked(self.mute_states[track])

    def highlight_current_song(self):
        self.clear_song_highlight()
        if 0 <= self.current_index < self.playlist_widget.count():
            item = self.playlist_widget.item(self.current_index)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(QColor("black"))
            item.setBackground(QColor("#eea1cd"))
            self.playlist_widget.setCurrentItem(item)

    def clear_song_highlight(self):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            font = item.font()
            font.setItalic(False)
            item.setFont(font)
            item.setForeground(QColor("white"))
            item.setBackground(QColor("transparent"))

    # ──────────────────────────────────────────────────────────────────────
    # ── Volumen ──────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def set_volume(self, value: int):
        self.volume = value
        # El volumen se aplica dinámicamente en _stream_writer, no se necesita
        # acción adicional aquí. Solo almacenamos el valor.

    def set_individual_volume(self, track_name: str, value: int):
        self.individual_volumes[track_name] = value / 100.0

    def toggle_mute(self):
        """Maneja el clic de cualquier botón de mute de pista."""
        sender = self.sender()
        btn_to_track = {
            self.drums_btn: "drums", self.vocals_btn: "vocals",
            self.bass_btn: "bass", self.other_btn: "other",
        }
        track_name = btn_to_track.get(sender)
        if not track_name:
            return
        self.mute_states[track_name] = not self.mute_states[track_name]
        muted = self.mute_states[track_name]
        icon_name = f"no_{track_name}" if muted else track_name
        sender.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))

    # ──────────────────────────────────────────────────────────────────────
    # ── Actualización de display ─────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def update_display(self):
        if self.playback_state != "Activa" or not self._track_data or self._seeking:
            return
        try:
            sr = self._track_data[0][1]
            total_frames = len(self._track_data[0][0])

            if self._seek_position >= total_frames:
                self.play_next()
                return

            current_ms = int((self._seek_position / sr) * 1000)
            self.progress_song.setValue(current_ms)

            current_s = current_ms // 1000
            if self._last_progress_seconds == current_s:
                return
            self._last_progress_seconds = current_s

            total_s = total_frames // sr
            cur_m, cur_s = divmod(current_s, 60)
            tot_m, tot_s = divmod(int(total_s), 60)
            self.progress_label.setText(
                f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}"
            )
        except Exception:
            self.stop_playback()

    def update_status(self):
        try:
            now = time.time()
            if now - self._last_stats_update > STATUS_CACHE_TTL:
                self._cached_stats = self.get_cache_stats()
                self._last_stats_update = now

            parts = [
                f"Canciones: {len(self.playlist)}",
                f"Reproducción: {self.playback_state.capitalize()}",
                self._format_demucs_progress(),
                f"En cola: {len(self.demucs_queue)}" if self.demucs_queue else "",
                f"Cache: {self._cached_stats.get('total_cached_items', 0)} elementos",
                f"Fecha: {datetime.now().strftime('%A - %d/%m/%Y')}",
                f"Hora: {datetime.now().strftime('%H:%M')}",
            ]
            self.status_label.setText(" | ".join(p for p in parts if p))
        except Exception:
            self.status_label.setText(
                f"Canciones: {len(self.playlist)} | Estado: {self.playback_state}"
            )

    def _format_demucs_progress(self) -> str:
        if self.demucs_active:
            filled = int(self.demucs_progress / 100 * 10)
            bar = '■' * filled + '▢' * (10 - filled)
            return f"Separando: {bar} {self.demucs_progress}%"
        if self.demucs_queue:
            return f"En cola: {len(self.demucs_queue)} trabajos"
        return ""

    # ──────────────────────────────────────────────────────────────────────
    # ── Botones e init de controles ──────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def init_leds(self) -> QHBoxLayout:
        def _make_btn(name, size, icon):
            btn = QPushButton()
            btn.setObjectName(name)
            btn.setFixedSize(*size)
            btn.setEnabled(False)
            bg_image(btn, f"images/main_window/{icon}.png")
            return btn

        self.prev_btn = _make_btn('prev_btn', (40, 40), 'prev')
        self.play_btn = _make_btn('play_btn', (80, 80), 'play')
        self.next_btn = _make_btn('next_btn', (40, 40), 'next')
        self.stop_btn = _make_btn('stop_btn', (40, 40), 'stop')

        self.volume_dial = CustomDial()
        self.volume_dial.setRange(0, 100)
        self.volume_dial.setValue(DEFAULT_VOLUME)
        self.volume_dial.setFixedSize(120, 120)
        self.volume_dial.setNotchesVisible(True)
        self.volume_dial.valueChanged.connect(self.set_volume)

        layout = QHBoxLayout()
        for w in (self.prev_btn, self.play_btn, self.next_btn,
                  self.stop_btn, self.volume_dial):
            layout.addWidget(w)
        return layout

    def track_buttons(self) -> QHBoxLayout:
        self._track_buttons: dict[str, QPushButton] = {}
        self._track_sliders: dict[str, QSlider] = {}

        outer = QHBoxLayout()
        for track in TRACK_NAMES:
            btn = QPushButton()
            self.setup_button(btn, f'{track}_btn', track)
            setattr(self, f'{track}_btn', btn)
            self._track_buttons[track] = btn

            slider = QSlider(Qt.Orientation.Horizontal)
            self.setup_slider(slider, track)
            setattr(self, f'{track}_slider', slider)
            self._track_sliders[track] = slider

            col = QVBoxLayout()
            col.addWidget(btn)
            col.addWidget(slider)
            outer.addLayout(col)

        self.mute_buttons = list(self._track_buttons.values())
        self.enable_disable_buttons(False)
        return outer

    def setup_button(self, button: QPushButton, object_name: str, icon_name: str):
        button.setObjectName(object_name)
        button.setIconSize(QSize(120, 120))
        button._icon_path = f'images/main_window/icons01/{icon_name}.png'
        button._icon_disabled = f'images/main_window/icons01/no_{icon_name}.png'
        self._lazy_load_icon(button, False)
        button.setCheckable(True)
        button.clicked.connect(self.toggle_mute)

    def setup_slider(self, slider: QSlider, track_name: str):
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedWidth(120)
        slider.valueChanged.connect(
            lambda v, t=track_name: self.set_individual_volume(t, v)
        )

    def _lazy_load_icon(self, btn: QPushButton, muted: bool):
        path = btn._icon_disabled if muted else btn._icon_path
        icon = self.lazy_images.load_icon_cached(resource_path(path), (120, 120))
        btn.setIcon(icon)

    def enable_disable_buttons(self, state: bool):
        for track in TRACK_NAMES:
            btn = self._track_buttons[track]
            btn.setEnabled(state)
            if state and not self.mute_states[track]:
                btn.setIcon(QIcon(resource_path(
                    f'images/main_window/icons01/{track}.png'
                )))
                btn.setChecked(False)

    def _set_playback_buttons_enabled(self, state: bool):
        for btn in (self.prev_btn, self.next_btn, self.play_btn):
            btn.setEnabled(state)

    # ──────────────────────────────────────────────────────────────────────
    # ── Playlist ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def load_folder(self, path: str = None):
        if not path:
            from os.path import expanduser
            path = QFileDialog.getExistingDirectory(
                self, "Seleccionar Carpeta", expanduser("~/Music")
            )
        if not path:
            return
        self.status_label.setText("Cargando playlist...")
        try:
            self.lazy_playlist.load_playlist_lazy(Path(path))
        except Exception as e:
            styled_message_box(
                self, "Error", f"Error iniciando carga: {str(e)}",
                QMessageBox.Icon.Critical,
            )
            self.status_label.setText("Error cargando playlist")

    def clear_playlist(self):
        self.stop_playback()
        self.playlist.clear()
        self.playlist_widget.clear()
        self.current_index = -1
        self._set_playback_buttons_enabled(False)
        self.stop_btn.setEnabled(False)

    def scan_folder(self, path: Path):
        icon = QIcon(resource_path('images/main_window/audio_icon.png'))
        for json_file in path.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dir_path = json_file.parent
                for artist, songs in data.items():
                    for song in songs:
                        if any(t['artist'] == artist and t['song'] == song
                               for t in self.playlist):
                            continue
                        self.playlist.append({"artist": artist, "song": song, "path": dir_path})
                        item = QListWidgetItem(f"{artist} - {song}")
                        item.setIcon(icon)
                        self.playlist_widget.addItem(item)
                        if not self.prev_btn.isEnabled():
                            self._set_playback_buttons_enabled(True)
                        self._check_and_fetch_lyrics_async(dir_path, artist, song)
            except Exception as e:
                styled_message_box(
                    self, "Error",
                    f"Error cargando {json_file}: {str(e)}",
                    QMessageBox.Icon.Critical,
                )
        self.update_status()

    def remove_selected(self):
        for item in self.playlist_widget.selectedItems():
            row = self.playlist_widget.row(item)
            self.playlist_widget.takeItem(row)
            del self.playlist[row]
        self.update_status()

    # ──────────────────────────────────────────────────────────────────────
    # ── Letras ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def load_lyrics(self, file_path):
        self.lyrics = []
        current_time = None
        current_text = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = re.match(r'\[(\d+):(\d+\.\d+)\]', line)
                if match:
                    if current_time is not None:
                        self.lyrics.append((current_time, '\n'.join(current_text)))
                    mins, secs = int(match.group(1)), float(match.group(2))
                    current_time = mins * 60 + secs
                    current_text = [line[match.end():]]
                elif current_time is not None and line:
                    current_text.append(line)

        if current_time is not None:
            self.lyrics.append((current_time, '\n'.join(current_text)))

        self.update_lyrics_menu_state()
        if not hasattr(self, 'lyrics_timer'):
            self.lyrics_timer = QTimer(self)
            self.lyrics_timer.timeout.connect(self.update_lyrics_display)
        self.lyrics_timer.start(100)

    def update_lyrics_display(self):
        if not self.lyrics or self.playback_state != "Activa":
            return
        current_time = self.progress_song.value() / 1000.0
        current_html = next_html = ""
        for i, (t, html) in enumerate(self.lyrics):
            if current_time >= t:
                current_html = html
                next_html = self.lyrics[i + 1][1] if i + 1 < len(self.lyrics) else ""
            else:
                break
        self.lyrics_current.setHtml(current_html)
        self.lyrics_next.setHtml(f'<center>{next_html}</center>')

    def update_lyrics_menu_state(self):
        enabled = (
            self.playback_state == "Activa"
            and self.current_index != -1
            and not self._lyrics_has_error()
        )
        self.advance_action.setEnabled(enabled)
        self.delay_action.setEnabled(enabled)

    def _lyrics_has_error(self) -> bool:
        if not self.lyrics or not isinstance(self.lyrics, list):
            return True
        error_keywords = ("no se encontraron", "letras no encontradas")
        return any(
            any(kw in html.lower() for kw in error_keywords)
            for _, html in self.lyrics
        )

    def adjust_lyrics_timing(self, offset: float):
        try:
            lrc_path = self.playlist[self.current_index]["path"] / "lyrics.lrc"
            with open(lrc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            modified = self._process_lines(lines, offset)
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.writelines(modified)
            self.load_lyrics(lrc_path)
        except Exception as e:
            styled_message_box(
                self, "Error", f"No se pudo ajustar: {str(e)}",
                QMessageBox.Icon.Warning,
            )

    def _process_lines(self, lines: list, offset: float) -> list:
        result = []
        for line in lines:
            if not line.strip().startswith("["):
                result.append(line)
                continue
            try:
                time_str = line[1:line.index("]")]
                new_time = self._adjust_time(time_str, offset)
                result.append(f"[{new_time}]{line.split(']', 1)[1]}")
            except Exception:
                result.append(line)
        return result

    def _adjust_time(self, time_str: str, offset: float) -> str:
        mins, rest = time_str.split(':', 1)
        secs, ms = rest.split('.', 1)
        total = max(0.0, int(mins) * 60 + int(secs) + int(ms) / 100 + offset)
        m, s = divmod(int(total), 60)
        centis = int((total - int(total)) * 100)
        return f"{m:02d}:{s:02d}.{centis:02d}"

    def increase_lyrics_font(self):
        self.lyrics_font_size = min(self.lyrics_font_size + 2, LYRICS_FONT_MAX)
        if self.lyrics_font_size > LYRICS_FONT_MAX:
            self.lyrics_font_size = LYRICS_FONT_MIN
        self.apply_lyrics_font()

    def decrease_lyrics_font(self):
        self.lyrics_font_size = max(self.lyrics_font_size - 2, LYRICS_FONT_MIN)
        if self.lyrics_font_size < LYRICS_FONT_MIN:
            self.lyrics_font_size = LYRICS_FONT_MAX
        self.apply_lyrics_font()

    def apply_lyrics_font(self):
        self.lyrics_current.setStyleSheet(
            f"QTextEdit {{ font-size: {self.lyrics_font_size}px; }}"
        )

    # ──────────────────────────────────────────────────────────────────────
    # ── Letras async ─────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _check_and_fetch_lyrics_async(self, dir_path, artist, song):
        def worker():
            lrc_path = Path(dir_path) / "lyrics.lrc"
            default_text = "Letras no encontradas, revisa datos de artista/canción"
            needs_update = not lrc_path.exists()
            if not needs_update:
                try:
                    needs_update = default_text in lrc_path.read_text(encoding="utf-8")
                except Exception:
                    needs_update = True
            if needs_update:
                self._fetch_lyrics_from_api(artist, song, Path(dir_path))

        threading.Thread(target=worker, daemon=True).start()

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize('NFKD', text.lower())
        return ''.join(c for c in normalized if not unicodedata.combining(c))

    def _fetch_lyrics_from_api(self, artist: str, song: str, output_dir: Path):
        url = f"https://lrclib.net/api/search?q={quote(f'{artist} {song}')}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            norm_artist = self._normalize_text(artist)
            norm_song = self._normalize_text(song)
            synced = ""
            for result in response.json():
                if (self._normalize_text(result.get("artistName", "")) == norm_artist
                        and self._normalize_text(result.get("trackName", "")) == norm_song
                        and result.get("syncedLyrics")):
                    synced = result["syncedLyrics"]
                    break
            self._write_lyrics_file(output_dir, artist, song, synced)
        except Exception:
            self._write_lyrics_file(output_dir, artist, song, None)

    def _write_lyrics_file(self, output_dir: Path, artist: str, song: str, lyrics):
        if not lyrics:
            content = '[00:00.00]<center style="color: #ff2626;">Letras no encontradas</center>\n'
        else:
            lines = []
            for line in lyrics.split('\n'):
                if line.strip():
                    parts = line.split(']', 1)
                    if len(parts) == 2:
                        lines.append(f'{parts[0]}]<center>{parts[1].strip()}</center>')
            content = '\n'.join(lines) + '\n'
        (output_dir / "lyrics.lrc").write_text(content, encoding="utf-8")

    # ──────────────────────────────────────────────────────────────────────
    # ── Metadatos ────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _update_metadata(self):
        try:
            for w in (self.lyrics_header, self.lyrics_current, self.lyrics_next):
                w.clear()
            song = self.playlist[self.current_index]
            path = Path(song["path"])
            lrc_path = path / "lyrics.lrc"
            self.title_bar.title.setText(f"{song['artist']} - {song['song']}")

            def load_cover():
                try:
                    self.cover_loaded.emit(
                        self.lazy_images.load_cover_lazy(path, (500, 500))
                    )
                except Exception as e:
                    print(f"Error cargando portada: {e}")

            def load_lyrics():
                try:
                    if not lrc_path.exists():
                        self.lyrics_not_found.emit()
                        return
                    self.lyrics_loaded.emit(self.lazy_lyrics.load_lyrics_lazy(path))
                except Exception as e:
                    self.lyrics_error.emit(str(e))

            threading.Thread(target=load_cover, daemon=True).start()
            threading.Thread(target=load_lyrics, daemon=True).start()
            self._preload_adjacent_resources()
        except Exception as e:
            print(f"Error actualizando metadatos: {e}")

    def _preload_adjacent_resources(self):
        if not self.playlist:
            return

        def worker():
            try:
                self.lazy_lyrics.preload_lyrics(self.playlist, self.current_index)
                for offset in (-1, 1):
                    idx = (self.current_index + offset) % len(self.playlist)
                    song_path = Path(self.playlist[idx]["path"])
                    key = f"cover_{song_path}_(500, 500)"
                    if key not in self.lazy_images.cache._cache:
                        self.lazy_images.load_cover_lazy(song_path, (500, 500))
            except Exception as e:
                print(f"Error en precarga: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # ── Demucs ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def show_split_dialog(self):
        if not self.demucs_available:
            styled_message_box(
                self, "Funcionalidad no disponible",
                "La separación de pistas requiere Demucs, pero no está instalado.\n\n"
                "Puede instalar Demucs y demás dependencias desde las opciones del menú.",
                QMessageBox.Icon.Warning,
            )
            return
        self.split_dialog = SplitDialog(self)
        bg_image(self.split_dialog, 'images/split_dialog/split.png')
        self.split_dialog.process_started.connect(self.process_song)
        self.split_dialog.show()

    def process_song(self, artist: str, song: str, file_path: str):
        self.last_in_queue = {"artist": artist, "song": song}
        self.demucs_queue.append({"artist": artist, "song": song, "file_path": file_path})
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
        self._start_demucs_job(self.demucs_queue.pop(0))

    def _start_demucs_job(self, job: dict):
        try:
            self._cleanup_demucs_job()
            self.demucs_active = True
            self.demucs_progress = 0
            self.processing = True
            self.update_status()

            self.demucs_worker = DemucsWorker(job['artist'], job['song'], job['file_path'])
            self.demucs_thread = QThread()
            self.demucs_worker.moveToThread(self.demucs_thread)
            self.demucs_thread.started.connect(self.demucs_worker.run)
            self.demucs_worker.finished.connect(self._on_demucs_success)
            self.demucs_worker.error.connect(self._handle_demucs_error)
            self.demucs_worker.progress.connect(self._update_demucs_progress)
            self.demucs_thread.finished.connect(self.demucs_thread.deleteLater)
            self.demucs_thread.start()
        except Exception as e:
            self._handle_demucs_error(f"Error iniciando separación: {e}")
            self._process_next_job()

    def _cleanup_demucs_job(self):
        try:
            if self.demucs_thread and self.demucs_thread.isRunning():
                self.demucs_thread.quit()
                self.demucs_thread.wait(1000)
        except Exception:
            pass
        try:
            if self.demucs_worker:
                self.demucs_worker.deleteLater()
        except Exception:
            pass
        self.demucs_thread = None
        self.demucs_worker = None

    def _on_demucs_success(self):
        self.scan_folder(DEFAULT_LIBRARY)
        self._finish_demucs_job()
        self._process_next_job()
        if not self.demucs_queue and self.processing_multiple:
            self.processing_multiple = False
            self._start_file_verification()

    def _finish_demucs_job(self):
        self.demucs_active = False
        self.processing = False
        self.update_status()
        if self.demucs_thread and self.demucs_thread.isRunning():
            self.demucs_thread.quit()
            self.demucs_thread.wait(500)
        self.demucs_thread = None
        self.demucs_worker = None

    def _handle_demucs_error(self, error_msg: str):
        self._finish_demucs_job()
        if not self.processing_multiple:
            styled_message_box(self, "Error", error_msg, QMessageBox.Icon.Critical)
        self._process_next_job()

    def _update_demucs_progress(self, value: int):
        self.demucs_progress = value
        self.update_status()

    # ──────────────────────────────────────────────────────────────────────
    # ── Verificación de archivos post-Demucs ─────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _start_file_verification(self):
        self._verification_attempts = 0
        self.verification_timer = QTimer(self)
        self.verification_timer.timeout.connect(self.check_files)
        self.verification_timer.start(VERIFICATION_INTERVAL_MS)
        self.check_files()

    def check_files(self):
        if self._verification_attempts >= VERIFICATION_MAX_ATTEMPTS:
            self.verification_timer.stop()
            self._verification_attempts = 0
            styled_message_box(
                self, "Timeout",
                f"No se pudieron verificar los archivos de:\n"
                f"{self.last_in_queue['artist']} - {self.last_in_queue['song']}\n\n"
                "Verifique manualmente la carpeta separated/",
                QMessageBox.Icon.Warning,
            )
            return

        if not self.last_in_queue.get('artist') or not self.last_in_queue.get('song'):
            self.verification_timer.stop()
            self._verification_attempts = 0
            return

        base = (DEFAULT_LIBRARY / self.last_in_queue['artist']
                / self.last_in_queue['song'] / "separated")
        required = ['drums.mp3', 'vocals.mp3', 'bass.mp3', 'other.mp3']

        if not base.exists() or not all((base / f).exists() for f in required):
            self._verification_attempts += 1
            return

        self.verification_timer.stop()
        self._verification_attempts = 0
        self.scan_folder(DEFAULT_LIBRARY)

    # ──────────────────────────────────────────────────────────────────────
    # ── Dependencias (multiplataforma) ───────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def load_demucs_model(self):
        """
        Verifica si Demucs está disponible.

        Analogía: Verificamos si el chef (Demucs) está en la cocina
        antes de aceptar pedidos de separación de pistas.
        """
        try:
            python = get_python_cmd()
            result = run_silent([python, '-m', 'demucs', '--help'], timeout=15)
            self.demucs_available = result.returncode == 0
        except Exception as e:
            Path("demucs_error.log").write_text(f"Error checking Demucs: {e}")
            self.demucs_available = False

    def _check_python_installation(self):
        self.python_available = check_command_exists(get_python_cmd())

    def _check_ffmpeg_installation(self):
        self.ffmpeg_available = check_command_exists('ffmpeg')

    def _check_vc_installation(self):
        """Solo se llama en Windows."""
        self.vc_available = check_visual_cpp()

    def _check_ytdlp_installation(self):
        self.ytdlp_available = check_command_exists('yt-dlp')

    def _check_gpu(self):
        self.gpu_available = detect_nvidia_gpu()

    def _check_pytorch_cuda(self):
        self.pytorch_cuda_available = check_pytorch_cuda()

    # ──────────────────────────────────────────────────────────────────────
    # ── Instaladores (patrón genérico) ───────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _confirm_install(self, description: str) -> bool:
        reply = styled_message_box(
            self, "Confirmar instalación",
            f"Se instalará {description}.\n"
            "Esto puede tomar varios minutos y puede requerir permisos de administrador.\n\n"
            "¿Desea continuar?",
            QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _start_worker_thread(self, worker, thread_attr: str, worker_attr: str,
                             on_finished, on_error, status_msg: str):
        """
        Lanza un worker en un QThread y conecta sus señales.

        Analogía: Es como contratar un técnico especializado — le damos
        la tarea, le decimos a quién avisarle cuando termine (on_finished)
        o si algo sale mal (on_error), y lo mandamos a trabajar.
        """
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        setattr(self, thread_attr, thread)
        setattr(self, worker_attr, worker)
        self.status_label.setText(status_msg)
        thread.start()

    def install_python(self):
        if self.python_available:
            return styled_message_box(
                self, "Python ya instalado", "Python ya está instalado.",
                QMessageBox.Icon.Information,
            )
        pkg = "Python" if IS_LINUX else "Python mediante winget"
        if not self._confirm_install(pkg):
            return
        self._start_worker_thread(
            PythonInstallWorker(), 'install_thread', 'install_worker',
            self._on_python_install_finished, self._on_python_install_error,
            "Instalando Python...",
        )

    def _on_python_install_finished(self):
        self.python_available = True
        self.status_label.setText("Python instalado correctamente.")
        self._update_python_menu_action()
        self._update_cuda_menu_action()
        styled_message_box(
            self, "Instalación completada",
            "Python se instaló correctamente.\n"
            "Es posible que necesite reiniciar la aplicación.",
            QMessageBox.Icon.Information,
        )

    def _on_python_install_error(self, msg: str):
        self.status_label.setText("Error instalando Python.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_vc(self):
        if self.vc_available:
            return styled_message_box(
                self, "Visual C++ ya instalado",
                "Visual C++ Redistributable ya está instalado.",
                QMessageBox.Icon.Information,
            )
        if not self._confirm_install("Microsoft Visual C++ Redistributable (x64) mediante winget"):
            return
        self._start_worker_thread(
            VisualCWorker(), 'vc_thread', 'vc_worker',
            self._on_vc_install_finished, self._on_vc_install_error,
            "Instalando Visual C++...",
        )

    def _on_vc_install_finished(self):
        self.vc_available = True
        self.status_label.setText("Visual C++ instalado correctamente.")
        self._update_vc_menu_action()
        self._update_demucs_menu_actions()
        self._update_cuda_menu_action()
        styled_message_box(
            self, "Instalación completada",
            "Visual C++ Redistributable se instaló correctamente.",
            QMessageBox.Icon.Information,
        )

    def _on_vc_install_error(self, msg: str):
        self.status_label.setText("Error instalando Visual C++.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_ffmpeg(self):
        if self.ffmpeg_available:
            return styled_message_box(
                self, "FFmpeg ya instalado", "FFmpeg ya está instalado.",
                QMessageBox.Icon.Information,
            )
        pkg = "FFmpeg" if IS_LINUX else "FFmpeg mediante winget"
        if not self._confirm_install(pkg):
            return
        self._start_worker_thread(
            FFmpegWorker(), 'ffmpeg_thread', 'ffmpeg_worker',
            self._on_ffmpeg_install_finished, self._on_ffmpeg_install_error,
            "Instalando FFmpeg...",
        )

    def _on_ffmpeg_install_finished(self):
        self.ffmpeg_available = True
        self.status_label.setText("FFmpeg instalado correctamente.")
        self._update_ffmpeg_menu_action()
        styled_message_box(
            self, "Instalación completada",
            "FFmpeg se instaló correctamente.",
            QMessageBox.Icon.Information,
        )

    def _on_ffmpeg_install_error(self, msg: str):
        self.status_label.setText("Error instalando FFmpeg.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_demucs(self):
        if self.demucs_available:
            return styled_message_box(
                self, "Demucs ya instalado", "Demucs ya está instalado.",
                QMessageBox.Icon.Information,
            )
        if not self.python_available:
            return styled_message_box(
                self, "Python requerido",
                "Debe instalar Python antes de instalar Demucs.",
                QMessageBox.Icon.Warning,
            )
        if self.demucs_install_in_progress:
            return styled_message_box(
                self, "Instalación en curso",
                "Ya hay una instalación de Demucs en progreso.",
                QMessageBox.Icon.Information,
            )
        if not self._confirm_install(
            "Demucs y el modelo htdemucs_ft (requiere internet)"
        ):
            return
        self.demucs_install_in_progress = True
        self._start_worker_thread(
            DemucsInstallWorker(), 'demucs_install_thread', 'demucs_install_worker',
            self._on_demucs_install_finished, self._on_demucs_install_error,
            "Instalando Demucs...",
        )

    def _on_demucs_install_finished(self):
        self.demucs_available = True
        self.demucs_install_in_progress = False
        self.status_label.setText("Demucs instalado correctamente.")
        self.load_demucs_model()
        self._update_demucs_menu_actions()
        styled_message_box(
            self, "Instalación completada",
            "Demucs se instaló y el modelo htdemucs_ft está listo.",
            QMessageBox.Icon.Information,
        )

    def _on_demucs_install_error(self, msg: str):
        self.demucs_install_in_progress = False
        self.status_label.setText("Error instalando Demucs.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_cuda(self):
        if self.pytorch_cuda_available:
            return styled_message_box(
                self, "CUDA ya instalado", "PyTorch+CUDA ya está instalado.",
                QMessageBox.Icon.Information,
            )
        if not self.python_available:
            return styled_message_box(
                self, "Python requerido", "Instale Python primero.",
                QMessageBox.Icon.Warning,
            )
        if not self.gpu_available:
            return styled_message_box(
                self, "Sin GPU NVIDIA",
                "No se detectó tarjeta NVIDIA compatible.",
                QMessageBox.Icon.Warning,
            )
        if self.cuda_install_in_progress:
            return styled_message_box(
                self, "Instalación en curso",
                "Ya hay una instalación de CUDA en progreso.",
                QMessageBox.Icon.Information,
            )
        if not self._confirm_install("PyTorch 2.6.0 con soporte CUDA 11.8"):
            return
        self.cuda_install_in_progress = True
        self._start_worker_thread(
            CudaInstallWorker(), 'cuda_thread', 'cuda_worker',
            self._on_cuda_install_finished, self._on_cuda_install_error,
            "Instalando CUDA (PyTorch)...",
        )

    def _on_cuda_install_finished(self):
        self.pytorch_cuda_available = True
        self.cuda_install_in_progress = False
        self.status_label.setText("CUDA instalado correctamente.")
        self._update_cuda_menu_action()
        styled_message_box(
            self, "Instalación completada",
            "PyTorch con CUDA se instaló correctamente.",
            QMessageBox.Icon.Information,
        )

    def _on_cuda_install_error(self, msg: str):
        self.cuda_install_in_progress = False
        self.status_label.setText("Error instalando CUDA.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_ytdlp(self):
        if self.ytdlp_available:
            return styled_message_box(
                self, "yt-dlp ya instalado", "yt-dlp ya está instalado.",
                QMessageBox.Icon.Information,
            )
        if not self._confirm_install("yt-dlp"):
            return
        self._start_worker_thread(
            YTDLPWorker(), 'ytdlp_thread', 'ytdlp_worker',
            self._on_ytdlp_install_finished, self._on_ytdlp_install_error,
            "Instalando yt-dlp...",
        )

    def _on_ytdlp_install_finished(self):
        self.ytdlp_available = True
        self.status_label.setText("yt-dlp instalado correctamente.")
        self._update_ytdlp_menu_actions()
        styled_message_box(
            self, "Instalación completada",
            "yt-dlp se instaló correctamente.\n"
            "Ahora puede usar 'Descargar MP3...'.",
            QMessageBox.Icon.Information,
        )

    def _on_ytdlp_install_error(self, msg: str):
        self.status_label.setText("Error instalando yt-dlp.")
        styled_message_box(self, "Error de instalación", msg, QMessageBox.Icon.Critical)

    # ──────────────────────────────────────────────────────────────────────
    # ── Descarga MP3 ─────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def download_mp3(self):
        if not self.ytdlp_available:
            styled_message_box(
                self, "yt-dlp no instalado",
                "Debe instalar yt-dlp primero desde Opciones > Dependencias.",
                QMessageBox.Icon.Warning,
            )
            return
        dialog = DownloadDialog(self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.download_requested.connect(self._start_ytdlp_download)
        dialog.exec()

    def _start_ytdlp_download(self, url: str):
        self._start_worker_thread(
            YTDLPDownloadWorker(url), 'download_thread', 'download_worker',
            self._on_download_finished, self._on_download_error,
            "Descargando MP3...",
        )

    def _on_download_finished(self, message: str):
        self.status_label.setText("Descarga completada.")
        styled_message_box(self, "Descarga finalizada", message, QMessageBox.Icon.Information)

    def _on_download_error(self, msg: str):
        self.status_label.setText("Error en descarga.")
        styled_message_box(self, "Error de descarga", msg, QMessageBox.Icon.Critical)

    # ──────────────────────────────────────────────────────────────────────
    # ── Menú ─────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def init_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("Archivo")
        options_menu = menu.addMenu("Opciones")
        help_menu = menu.addMenu("Ayuda")

        # Archivo
        load_action = QAction("Seleccionar Carpeta", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self.load_folder)
        file_menu.addAction(load_action)

        self.split_action = QAction("Dividir...", self)
        self.split_action.setShortcut(QKeySequence("Ctrl+D"))
        self.split_action.triggered.connect(self.show_split_dialog)
        self.split_action.setEnabled(self.demucs_available)
        if not self.demucs_available:
            self.split_action.setToolTip("Demucs no está instalado o no es accesible")
        file_menu.addAction(self.split_action)
        file_menu.addSeparator()

        remove_action = QAction("Remover de PlayList", self)
        remove_action.triggered.connect(self.remove_selected)
        file_menu.addAction(remove_action)

        clear_playlist_action = QAction("Limpiar Playlist", self)
        clear_playlist_action.triggered.connect(self.clear_playlist)
        file_menu.addAction(clear_playlist_action)
        file_menu.addSeparator()

        exit_action = QAction("&Salir", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)

        # Opciones
        self.show_playlist_action = QAction("Mostrar lista", self)
        self.show_playlist_action.setCheckable(True)
        self.show_playlist_action.setChecked(True)
        self.show_playlist_action.triggered.connect(self._toggle_playlist_visibility)
        options_menu.addAction(self.show_playlist_action)

        lyrics_menu = options_menu.addMenu("Modificar Lyrics")
        self.advance_action = QAction(">> Mostrar Después 0.5s", self)
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
        for a in (self.advance_action, self.delay_action):
            lyrics_menu.addAction(a)
            a.setEnabled(False)
        lyrics_menu.addSeparator()
        lyrics_menu.addAction(self.increase_font_action)
        lyrics_menu.addAction(self.decrease_font_action)

        cleanup_action = QAction("Limpiar Cache", self)
        cleanup_action.triggered.connect(self.cleanup_resources_manual)
        options_menu.addAction(cleanup_action)

        # Dependencias
        deps_menu = options_menu.addMenu("Dependencias")
        dep_specs = [
            ("install_python_action", "Instalar Python", self.install_python,
             not self.python_available),
            ("install_ffmpeg_action", "Instalar FFmpeg", self.install_ffmpeg,
             not self.ffmpeg_available),
            ("install_demucs_action", "Instalar Demucs", self.install_demucs,
             self.python_available and not self.demucs_available),
            ("install_cuda_action", "Instalar CUDA (GPU Nvidia necesario)", self.install_cuda,
             self.python_available and self.gpu_available and not self.pytorch_cuda_available),
        ]

        # Visual C++ solo aparece en Windows
        if IS_WINDOWS:
            dep_specs.insert(1, (
                "install_vc_action", "Instalar Visual C++", self.install_vc,
                not self.vc_available,
            ))

        for attr, label, slot, enabled in dep_specs:
            action = QAction(label, self)
            action.triggered.connect(slot)
            action.setEnabled(enabled)
            deps_menu.addAction(action)
            setattr(self, attr, action)

        deps_menu.addSeparator()
        self.install_ytdlp_action = QAction("Instalar YT-DLP (Youtube → MP3)", self)
        self.install_ytdlp_action.triggered.connect(self.install_ytdlp)
        self.install_ytdlp_action.setEnabled(not self.ytdlp_available)
        deps_menu.addAction(self.install_ytdlp_action)

        options_menu.addSeparator()
        self.download_mp3_action = QAction("Descargar MP3...", self)
        self.download_mp3_action.triggered.connect(self.download_mp3)
        self.download_mp3_action.setEnabled(self.ytdlp_available)
        options_menu.addAction(self.download_mp3_action)

        # Ayuda
        about_action = QAction("Sobre Playit", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        queue_action = QAction("Mostrar Queue", self)
        queue_action.triggered.connect(self.show_queue_dialog)
        help_menu.addAction(queue_action)

    # ──────────────────────────────────────────────────────────────────────
    # ── Actualizaciones de menú ──────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _update_python_menu_action(self):
        if hasattr(self, 'install_python_action'):
            self.install_python_action.setEnabled(not self.python_available)
            self._update_demucs_menu_actions()

    def _update_vc_menu_action(self):
        if hasattr(self, 'install_vc_action'):
            self.install_vc_action.setEnabled(not self.vc_available)

    def _update_ffmpeg_menu_action(self):
        if hasattr(self, 'install_ffmpeg_action'):
            self.install_ffmpeg_action.setEnabled(not self.ffmpeg_available)

    def _update_demucs_menu_actions(self):
        if hasattr(self, 'install_demucs_action'):
            self.install_demucs_action.setEnabled(
                self.python_available and self.ffmpeg_available
                and not self.demucs_available
            )
        if hasattr(self, 'split_action'):
            self.split_action.setEnabled(self.demucs_available)

    def _update_cuda_menu_action(self):
        if hasattr(self, 'install_cuda_action'):
            self.install_cuda_action.setEnabled(
                self.python_available and self.gpu_available
                and not self.pytorch_cuda_available
            )

    def _update_ytdlp_menu_actions(self):
        if hasattr(self, 'install_ytdlp_action'):
            self.install_ytdlp_action.setEnabled(not self.ytdlp_available)
        if hasattr(self, 'download_mp3_action'):
            self.download_mp3_action.setEnabled(self.ytdlp_available)

    def _toggle_playlist_visibility(self, state: bool):
        self.playlist_dock.setVisible(state)

    def _update_playlist_menu_state(self, visible: bool):
        self.show_playlist_action.setChecked(visible)

    # ──────────────────────────────────────────────────────────────────────
    # ── Barra de estado ──────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def init_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel()
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_bar.addPermanentWidget(self.status_label, stretch=1)
        self.status_bar.showMessage("Listo", 3000)
        self.update_status()

    # ──────────────────────────────────────────────────────────────────────
    # ── Caché ────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def get_cache_stats(self) -> dict:
        try:
            a = self.lazy_audio.cache.get_stats()
            i = self.lazy_images.cache.get_stats()
            lyr = self.lazy_lyrics.cache.get_stats()
            total_hits = a['hits'] + i['hits'] + lyr['hits']
            total_req = total_hits + a['misses'] + i['misses'] + lyr['misses']
            return {
                "audio_cache": a, "image_cache": i, "lyrics_cache": lyr,
                "total_cached_items": a['size'] + i['size'] + lyr['size'],
                "overall_hit_rate": total_hits / max(1, total_req) * 100,
                "memory_utilization": {
                    "audio": a['utilization'],
                    "images": i['utilization'],
                    "lyrics": lyr['utilization'],
                },
            }
        except Exception as e:
            return {
                "error": str(e), "total_cached_items": 0,
                "overall_hit_rate": 0,
                "memory_utilization": {"audio": 0, "images": 0, "lyrics": 0},
            }

    def cleanup_resources_manual(self):
        try:
            before = self.get_cache_stats()
            for cache in (self.lazy_audio.cache, self.lazy_images.cache,
                          self.lazy_lyrics.cache):
                cache.clear()
            after = self.get_cache_stats()
            freed = before['total_cached_items'] - after['total_cached_items']
            styled_message_box(
                self, "Limpieza Completa",
                f"Cache limpiado exitosamente.\n"
                f"Elementos eliminados: {freed}\n"
                f"Memoria liberada aproximada: {freed * 2:.1f}MB",
            )
        except Exception as e:
            styled_message_box(
                self, "Error", f"Error durante la limpieza: {e}",
                QMessageBox.Icon.Warning,
            )
        self.update_status()

    # ──────────────────────────────────────────────────────────────────────
    # ── Diálogos ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def show_about_dialog(self):
        dialog = AboutDialog(self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    def show_queue_dialog(self):
        dialog = QueueDialog(self, parent=self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    # ──────────────────────────────────────────────────────────────────────
    # ── Utilidades ───────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _create_json(self, path: Path, artist: str, song: str, config: dict):
        data = {artist: {song: {k: str(v) for k, v in config.items()}}}
        (path / "data.json").write_text(json.dumps(data, indent=4))

    def close_application(self):
        QApplication.instance().quit()
