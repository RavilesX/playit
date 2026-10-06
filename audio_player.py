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

import threading
import logging
import random
import re
from pathlib import Path
import json
from datetime import datetime
import time
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QPoint, QEvent, QUrl
from PyQt6.QtGui import (QAction, QActionGroup, QPixmap, QKeySequence, QColor, QPainter,
                         QIcon, QImage, QShortcut, QDesktopServices)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QListWidget, QDockWidget, QTabWidget, QLabel, QTextEdit,
    QPushButton, QSlider, QStatusBar, QMessageBox,
    QFrame, QListWidgetItem, QWidget, QFileDialog,
    QAbstractItemView, QCheckBox, QMenu, QDialog,
)
import sounddevice as sd
import soundfile as sf
import numpy as np
from platform_utils import IS_WINDOWS, IS_MAC, get_data_dir
from demucs_worker import _sanitize_path_component
from demucs_queue import DemucsQueue
from lyrics_api import LYRICS_NOT_FOUND_TEXT, LyricsFetchQueue, fetch_lyrics, normalize_text
import shutil
from base_worker import start_worker_thread
from dependencies import DependencyManager
from ytdlp_download_worker import YTDLPDownloadWorker
from update_check_worker import UpdateCheckWorker
from version import __version__
from i18n import N_, SUPPORTED, current_language, qlocale, tr
from settings import save_setting
from resources import styled_message_box, bg_image, resource_path, style_url
from ui_components import TitleBar, CustomDial, SizeGrip, PlaylistItemDelegate
from dialogs import (
    AboutDialog, QueueDialog, SplitDialog, DownloadDialog, SearchDialog,
    UpdateDialog, CorrectSongDialog, SongInfoDialog, RemotePairDialog,
    PlaybackQueueDialog,
)
from remote_server import RemoteBridge, RemoteServer
from lazy_resources import (LazyAudioManager, LazyImageManager, LazyLyricsManager,
                            LazyPlaylistLoader, get_song_duration,
                            read_mlst, read_song_metadata, write_mlst)
from audio_visualizer import (AudioAnalyzer, CircularVisualizerWidget,
                              VisualizerWidget)
from lyrics_sync_editor import AUTO_UNMUTE_COLOR, LYRIC_COLORS, LyricsSyncDialog

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# ── Constantes ────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
TRACK_NAMES = ("drums", "vocals", "bass", "other")
DEFAULT_LIBRARY = get_data_dir() / "music_library"
DEFAULT_VOLUME = 25
LYRICS_FONT_MIN = 20
LYRICS_FONT_MAX = 100
LYRICS_FONT_DEFAULT = 62
LYRICS_NEXT_MIN_HEIGHT = 60
STATUS_CACHE_TTL = 5.0


class AudioPlayer(QMainWindow):
    # QImage (no QPixmap): la portada se carga en hilos secundarios y Qt solo
    # permite crear QPixmap en el hilo de la GUI
    cover_loaded = pyqtSignal(QImage)
    lyrics_loaded = pyqtSignal(list)
    lyrics_error = pyqtSignal(str)
    lyrics_not_found = pyqtSignal()
    lyrics_refetched = pyqtSignal(str, bool)  # ruta de la canción, encontradas

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
            with open(resource_path('estilos.css'), 'r') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            styled_message_box(
                self, tr("Error de estilos"),
                tr("Archivo de estilos no encontrado"),
                QMessageBox.Icon.Critical,
            )

    def _initialize_state_variables(self):
        # Playlist
        self.playlist: list[dict] = []
        self._playlist_keys: set[tuple[str, str]] = set()
        self.current_index = -1
        self.playback_state = "Detenido"
        self.current_channels: list = []
        self._repeat = False
        self._current_mlst_path = None

        # Cola de reproducción ("Agregar a la cola"): canciones a reproducir
        # a continuación, por identidad (mismos dicts que self.playlist) para
        # sobrevivir sort/remove sin recalcular índices.
        self.play_queue: list[dict] = []

        # Modo remoto (control desde PlayIt Mobile)
        # _playlist_rev le dice al móvil "la lista cambió, volvé a pedirla"
        self._playlist_rev = 0
        self._remote_bridge = None
        self._remote_server = None

        # Búsqueda en playlist
        self._search_query = ""
        self._search_matches: list[int] = []
        self._search_pos = -1

        # Cola de letras: un solo worker en segundo plano para no saturar
        # red/CPU al cargar playlists grandes
        self._lyrics_fetch = LyricsFetchQueue()

        # Cola Demucs
        self.demucs = DemucsQueue(self, DEFAULT_LIBRARY)
        self.demucs.changed.connect(self.update_status)
        self.demucs.song_ready.connect(self.scan_folder)

        # Audio / volumen
        self.volume = DEFAULT_VOLUME
        self.individual_volumes = {t: 1.0 for t in TRACK_NAMES}
        self.mute_states = {t: False for t in TRACK_NAMES}
        # Auto-unmute de voz en líneas en blanco de las letras (con fundido)
        self.auto_unmute_enabled = False
        self._auto_unmute_gain = 0.0  # ganancia actual de la voz (0..1)
        self._seeking = False
        self._sd_streams: list = []
        # Stems de la canción cargada (orden TRACK_NAMES) y datos de su header;
        # el audio se decodifica por bloques en _stream_writer
        self._track_paths: list[Path] = []
        self._sr = 0
        self._channels = 0
        self._total_frames = 0
        self._seek_position = 0
        self._stream_lock = threading.Lock()
        self._stream_cancel_flags: list = []
        self._writer_thread = None
        self._stream_pause_flag = threading.Event()
        self._stream_pause_flag.set()

        # Letras
        self.lyrics: list = []
        self.lyrics_font_size = LYRICS_FONT_DEFAULT
        self._last_current_html = None
        self._last_progress_seconds = -1

        # Diálogos
        self.split_dialog = None

        # Atributos creados dinámicamente (setattr) en track_buttons();
        # declarados aquí para el type checker
        self.drums_btn: QPushButton
        self.vocals_btn: QPushButton
        self.bass_btn: QPushButton
        self.other_btn: QPushButton

        # Caché de status
        self._last_stats_update = 0.0
        self._cached_stats: dict = {"total_cached_items": 0}

    def _setup_audio_system(self):
        self.deps = DependencyManager(self)
        self.deps.changed.connect(self._update_dependency_menus)
        self.deps.check_async()

    def _update_dependency_menus(self):
        d = self.deps
        self.install_python_action.setEnabled(not d.python_available)
        self.install_ffmpeg_action.setEnabled(not d.ffmpeg_available)
        self.install_demucs_action.setEnabled(
            d.python_available and d.ffmpeg_available and not d.demucs_available)
        self.split_action.setEnabled(d.demucs_available)
        self.install_ytdlp_action.setEnabled(not d.ytdlp_available)
        self.download_mp3_action.setEnabled(d.ytdlp_available)
        # Visual C++ solo existe en Windows; CUDA no existe en macOS
        if IS_WINDOWS:
            self.install_vc_action.setEnabled(not d.vc_available)
        if not IS_MAC:
            self.install_cuda_action.setEnabled(
                d.python_available and d.gpu_available and not d.pytorch_cuda_available)

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
        self._create_visualizer()
        self.init_menu()
        self.init_status_bar()

    def _create_visualizer(self):
        # Analizador en NumPy (corre en el hilo de audio); el widget pinta detrás de
        # los controles. La señal cruza al hilo GUI de forma segura (QueuedConnection).
        self.analyzer = AudioAnalyzer(parent=self)
        self.visualizer = VisualizerWidget(self.main_frame)
        self.analyzer.bars_ready.connect(self.visualizer.set_bars)
        self.visualizer.lower()
        # El frame central se redimensiona al mostrar/ocultar el dock de la
        # playlist sin disparar el resizeEvent de la ventana; el filtro reubica
        # el visualizador en cada resize del frame para que ocupe todo el ancho.
        self.main_frame.installEventFilter(self)
        QTimer.singleShot(0, self._position_visualizer)

    def eventFilter(self, obj, event):
        if obj is getattr(self, 'main_frame', None) and \
                event.type() == QEvent.Type.Resize:
            self._position_visualizer()
        if event.type() == QEvent.Type.MouseButtonDblClick and \
                obj in getattr(self, '_lyrics_click_areas', ()):
            self._toggle_lyrics_fullscreen()
            return True
        # Recentrar el visualizador circular si la ventana fullscreen cambia
        # de tamaño (p. ej. al moverse a otro monitor).
        if obj is getattr(self, 'lyrics_container', None) and \
                event.type() == QEvent.Type.Resize and \
                getattr(self, '_lyrics_fullscreen', False):
            self._position_fs_visualizer()
        return super().eventFilter(obj, event)

    def _toggle_visualizer(self, enabled: bool):
        # Desactiva el DSP (no se alimenta el analizador) y oculta el widget.
        if hasattr(self, 'analyzer'):
            self.analyzer.enabled = enabled
        if hasattr(self, 'visualizer'):
            self.visualizer.clear()
            self.visualizer.setVisible(enabled)
        if self._fs_visualizer is not None:
            self._fs_visualizer.clear()
            self._fs_visualizer.setVisible(enabled)

    def _position_visualizer(self):
        # Ocupa desde el borde superior de la barra de progreso hasta el fondo del
        # frame: las barras suben desde abajo con altura máxima en la barra de progreso.
        if not hasattr(self, 'visualizer'):
            return
        top = self.progress_song.mapTo(self.main_frame, QPoint(0, 0)).y()
        frame_h = self.main_frame.height()
        frame_w = self.main_frame.width()
        height = max(0, frame_h - top - 2)
        self.visualizer.setGeometry(2, top, frame_w - 4, height)
        self.visualizer.lower()

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
        # macOS recorta el texto de las pestañas con "…" (elide); en
        # Windows/Linux no pasa. Sin elide + min-width en el QSS se ven completas.
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)

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
        self.lyrics_next.setFixedHeight(LYRICS_NEXT_MIN_HEIGHT)
        self.lyrics_next.setObjectName("lyrics_next")
        self.lyrics_next.setStyleSheet("background: transparent; border: none;")

        lyrics_layout = QVBoxLayout()
        lyrics_layout.setContentsMargins(0, 0, 0, 0)
        for w in (self.lyrics_header, self.lyrics_current, self.lyrics_next):
            lyrics_layout.addWidget(w)

        self.lyrics_container = QWidget()
        self.lyrics_container.setLayout(lyrics_layout)

        # Letras en pantalla completa: Esc sale (atajo con alcance al contenedor
        # y sus hijos, para que funcione con el foco en cualquier QTextEdit);
        # doble clic sobre la sección entra/sale (ver eventFilter).
        self._lyrics_fullscreen = False
        self._fs_visualizer = None
        self._fs_viz_style = "wave"
        self._fs_toast = None
        self._fs_toast_timer = None
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.lyrics_container)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._exit_lyrics_fullscreen)
        self._lyrics_click_areas = tuple(
            w.viewport() for w in
            (self.lyrics_header, self.lyrics_current, self.lyrics_next)
        ) + (self.lyrics_container,)
        for w in self._lyrics_click_areas:
            if w is not None:
                w.installEventFilter(self)

        self.tabs.addTab(self.lyrics_container, tr("Letras"))
        self.tabs.addTab(self.cover_label, tr("Portada"))
        # Portada visible al iniciar; al reproducir una canción se
        # cambia automáticamente a Letras (ver play_current)
        self.tabs.setCurrentWidget(self.cover_label)

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

    # Modos de ordenamiento que recorre el botón toggle (key, reverse, etiqueta)
    _SORT_MODES = (
        ("artist", False, N_("Artista A-Z")),
        ("artist", True, N_("Artista Z-A")),
        ("song", False, N_("Título A-Z")),
        ("song", True, N_("Título Z-A")),
        ("random", False, N_("Aleatorio")),
    )

    def _create_playlist_dock(self):
        self.playlist_dock = QDockWidget(self)
        self.playlist_widget = QListWidget()
        self.playlist_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.playlist_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.playlist_widget.setFixedWidth(500)
        self.playlist_widget.setUniformItemSizes(True)
        self.playlist_widget.setItemDelegate(PlaylistItemDelegate(self.playlist_widget))
        self._audio_icon = QIcon(resource_path('images/main_window/audio_icon.png'))

        # Contenedor: mini barra de herramientas arriba + lista debajo
        container = QWidget()
        container.setFixedWidth(500)
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)
        vbox.addLayout(self._create_playlist_toolbar())
        vbox.addWidget(self.playlist_widget)

        self.playlist_dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.playlist_dock)

    def _create_playlist_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.setSpacing(4)

        self._sort_mode = -1  # -1 = sin orden (carpeta recién cargada)

        folder_btn = QPushButton(tr("Seleccionar carpeta"))
        folder_btn.setObjectName("playlistToolBtn")
        folder_btn.clicked.connect(lambda: self.load_folder())

        load_btn = QPushButton(tr("Cargar playlist"))
        load_btn.setObjectName("playlistToolBtn")
        load_btn.clicked.connect(self.load_playlist_mlst)

        clear_btn = QPushButton(tr("Limpiar"))
        clear_btn.setObjectName("playlistToolBtn")
        clear_btn.clicked.connect(self.clear_playlist)

        self.sort_toggle_btn = QPushButton(tr("Ordenar"))
        self.sort_toggle_btn.setObjectName("playlistToolBtn")
        self.sort_toggle_btn.clicked.connect(self._cycle_sort)

        self.sort_label = QLabel(tr("Sin orden"))
        self.sort_label.setObjectName("playlistSortLabel")

        for w in (folder_btn, load_btn, clear_btn, self.sort_toggle_btn):
            toolbar.addWidget(w)
        toolbar.addWidget(self.sort_label)
        toolbar.addStretch()
        return toolbar

    def _reset_sort_label(self):
        self._sort_mode = -1
        self.sort_label.setText(tr("Sin orden"))

    def _cycle_sort(self):
        next_mode = (self._sort_mode + 1) % len(self._SORT_MODES)
        key, reverse, _ = self._SORT_MODES[next_mode]
        self.sort_playlist(key, reverse=reverse)

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
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        self.progress_song.sliderMoved.connect(self._on_progress_moved)
        self.progress_song.sliderReleased.connect(self._on_progress_released)
        self.progress_song.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _connect_playlist_events(self):
        self.playlist_widget.itemActivated.connect(self.play_selected)
        self.playlist_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(
            self._show_playlist_context_menu
        )

    def _show_playlist_context_menu(self, pos: QPoint):
        item = self.playlist_widget.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self.playlist_widget)
        open_folder_action = menu.addAction(tr("Ir a la carpeta"))
        correct_action = menu.addAction(tr("Corregir"))
        # Solo para mostrar "F2" en el menú: el atajo real lo maneja
        # keyPressEvent (el QMenu es temporal y muere con el exec()).
        correct_action.setShortcut(QKeySequence("F2"))
        correct_action.setShortcutVisibleInContextMenu(True)
        refetch_lyrics_action = menu.addAction(tr("Buscar letras de nuevo"))
        info_action = menu.addAction(tr("Información"))

        copy_menu = menu.addMenu(tr("Copiar"))
        copy_artist_action = copy_menu.addAction(tr("Artista"))
        copy_song_action = copy_menu.addAction(tr("Canción"))
        copy_artist_song_action = copy_menu.addAction(tr("Artista - Canción"))
        copy_path_action = copy_menu.addAction(tr("Ruta"))

        menu.addSeparator()
        # Con selección múltiple, "Agregar/Eliminar de la cola" actúa sobre
        # todos los ítems seleccionados, no solo el que recibió el clic.
        target_songs = self._queue_action_targets(item)
        add_mode = not (target_songs and all(self._is_queued(s) for s in target_songs))
        queue_action = menu.addAction(
            tr("Agregar a la cola") if add_mode else tr("Eliminar de la cola")
        )
        manage_queue_action = menu.addAction(tr("Administrar cola"))

        action = menu.exec(self.playlist_widget.mapToGlobal(pos))

        if action == open_folder_action:
            self._open_song_folder(item)
        elif action == correct_action:
            self._correct_song(item)
        elif action == refetch_lyrics_action:
            self._force_fetch_lyrics(item)
        elif action == info_action:
            self._show_song_info(item)
        elif action == copy_artist_action:
            self._copy_song_info(item, 'artist')
        elif action == copy_song_action:
            self._copy_song_info(item, 'song')
        elif action == copy_artist_song_action:
            self._copy_song_info(item, 'artist_song')
        elif action == copy_path_action:
            self._copy_song_info(item, 'path')
        elif action == queue_action:
            self._toggle_queue_many(target_songs, add_mode)
        elif action == manage_queue_action:
            self._show_queue_manager()

    # ──────────────────────────────────────────────────────────────────────
    # ── Cola de reproducción ("Agregar a la cola") ───────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _is_queued(self, song_data: dict) -> bool:
        return any(s is song_data for s in self.play_queue)

    def _refresh_queue_indicators(self):
        """Sincroniza el punto morado de "en cola" de cada renglón de la
        playlist con self.play_queue. Se llama después de cualquier cambio
        a la cola (agregar/quitar/consumir), nunca desde el paint() del
        delegate — ahí sería recalcular la pertenencia en cada repintado."""
        for row, song in enumerate(self.playlist):
            item = self.playlist_widget.item(row)
            if item is not None:
                item.setData(PlaylistItemDelegate.QUEUE_ROLE, self._is_queued(song))
        # Empuje inmediato al móvil: sin esto la cola solo se actualizaría en
        # el tick de 1 s de remote_timer, y un cambio hecho en el Desktop se
        # vería con hasta un segundo de retraso.
        self._publish_remote_state()

    def _toggle_queue(self, song_data: dict | None):
        if song_data is None:
            return
        if self._is_queued(song_data):
            self.play_queue[:] = [s for s in self.play_queue if s is not song_data]
        else:
            self.play_queue.append(song_data)
        self._refresh_queue_indicators()

    def _queue_action_targets(self, item: QListWidgetItem) -> list[dict]:
        """Canciones objetivo de Agregar/Eliminar de la cola: toda la
        selección múltiple si el ítem clickeado forma parte de ella, si no
        solo ese ítem (clic derecho fuera de la selección actual)."""
        selected_items = self.playlist_widget.selectedItems()
        items = selected_items if item in selected_items and len(selected_items) > 1 else [item]
        songs = []
        for it in items:
            row = self.playlist_widget.row(it)
            if 0 <= row < len(self.playlist):
                songs.append(self.playlist[row])
        return songs

    def _toggle_queue_many(self, songs: list[dict], add: bool):
        for song in songs:
            if add and not self._is_queued(song):
                self.play_queue.append(song)
            elif not add and self._is_queued(song):
                self.play_queue[:] = [s for s in self.play_queue if s is not song]
        self._refresh_queue_indicators()

    def _purge_queue(self):
        """Descarta de la cola las canciones que ya no están en la playlist."""
        self.play_queue[:] = [
            s for s in self.play_queue if any(s is p for p in self.playlist)
        ]
        self._refresh_queue_indicators()

    def _show_queue_manager(self):
        dialog = PlaybackQueueDialog(self, parent=self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    def _copy_song_info(self, item: QListWidgetItem, kind: str):
        artist, _, song = item.text().partition(" - ")
        if kind == 'artist':
            text = artist
        elif kind == 'song':
            text = song
        elif kind == 'artist_song':
            text = item.text()
        else:
            raw = item.data(PlaylistItemDelegate.PATH_ROLE)
            text = str(Path(raw).resolve()) if raw else ''
        QApplication.clipboard().setText(text)

    def _show_song_info(self, item: QListWidgetItem):
        """Información de la canción: artista y canción salen de la estructura
        del data.json (las claves con las que entró a la playlist), el resto de
        su bloque "metadata"."""
        row = self.playlist_widget.row(item)
        song_data = self.playlist[row] if 0 <= row < len(self.playlist) else {}
        folder = item.data(PlaylistItemDelegate.PATH_ROLE)
        metadata = read_song_metadata(Path(folder)) if folder else {}
        dialog = SongInfoDialog(
            self, song_data.get('artist', ''), song_data.get('song', ''), metadata
        )
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    def _open_song_folder(self, item: QListWidgetItem):
        folder = item.data(PlaylistItemDelegate.PATH_ROLE)
        if not folder or not Path(folder).is_dir():
            styled_message_box(
                self, tr("Carpeta no encontrada"),
                tr("No se encontró la carpeta de esta canción."),
                QMessageBox.Icon.Warning,
            )
            return
        # PATH_ROLE puede quedar relativo al cwd (get_data_dir() en
        # Windows/Linux devuelve Path('.')): resolver a absoluto, si no
        # QDesktopServices arma un file: URI inválido (sin "/" inicial) y
        # no hace nada en binarios empaquetados.
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(folder).resolve()))):
            styled_message_box(
                self, tr("Error"),
                tr("No se pudo abrir la carpeta con el explorador de archivos."),
                QMessageBox.Icon.Warning,
            )

    def _correct_selected(self):
        """Corregir la canción seleccionada (F2)."""
        item = self.playlist_widget.currentItem()
        if item is not None and item.isSelected():
            self._correct_song(item)

    def _correct_song(self, item: QListWidgetItem):
        row = self.playlist_widget.row(item)
        if not (0 <= row < len(self.playlist)):
            return
        song_data = self.playlist[row]
        old_path = Path(song_data['path'])
        if not old_path.is_dir():
            styled_message_box(
                self, tr("Carpeta no encontrada"),
                tr("No se encontró la carpeta de esta canción."),
                QMessageBox.Icon.Warning,
            )
            return

        dialog = CorrectSongDialog(self, song_data['artist'], song_data['song'])
        bg_image(dialog, 'images/split_dialog/split.png')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_artist, new_song = dialog.get_values()
        if new_artist == song_data['artist'] and new_song == song_data['song']:
            return

        # La canción puede vivir en una librería distinta a DEFAULT_LIBRARY
        # (playlist cargada desde otra carpeta/disco): la nueva ruta se arma
        # sobre la raíz real (<libreria>/<artista>/<canción>), si no el move
        # cruzaría dispositivos y fallaría.
        library_root = old_path.parent.parent
        new_path = (
            library_root
            / _sanitize_path_component(new_artist) / _sanitize_path_component(new_song)
        )

        if new_path != old_path and new_path.exists():
            reply = styled_message_box(
                self, tr("Carpeta existente"),
                tr('Ya existe una carpeta para "{artist} - {song}".\n'
                   "¿Combinar y sobrescribir los archivos con el mismo nombre?"
                   ).format(artist=new_artist, song=new_song),
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Cerrar streams antes de mover archivos: en Windows un stream con el
        # archivo abierto bloquea el move/rename.
        if row == self.current_index and self.playback_state != "Detenido":
            self.stop_playback()

        try:
            if new_path != old_path:
                self._move_song_folder(old_path, new_path)
            json_data = self._write_song_metadata(new_path, new_artist, new_song)
        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("No se pudo corregir la canción:\n{error}").format(error=e),
                QMessageBox.Icon.Critical,
            )
            return

        self._playlist_keys.discard((song_data['artist'], song_data['song']))
        self._playlist_keys.add((new_artist, new_song))
        song_data['artist'] = new_artist
        song_data['song'] = new_song
        song_data['path'] = new_path
        song_data['json_data'] = json_data

        item.setText(f"{new_artist} - {new_song}")
        item.setData(PlaylistItemDelegate.PATH_ROLE, str(new_path))

        self._bump_playlist_rev()
        self.show_status_message(
            tr("Corregido: {artist} - {song}").format(artist=new_artist, song=new_song))

    def _force_fetch_lyrics(self, item: QListWidgetItem):
        """Vuelve a buscar letras en la API ignorando el lyrics.lrc existente.

        Útil tras corregir el artista/canción: la búsqueda automática solo
        corre si el archivo no existe o dice "no encontradas", así que un
        .lrc equivocado nunca se reemplazaría solo.
        """
        row = self.playlist_widget.row(item)
        if not (0 <= row < len(self.playlist)):
            return
        song_data = self.playlist[row]
        path = Path(song_data['path'])
        if not path.is_dir():
            styled_message_box(
                self, tr("Carpeta no encontrada"),
                tr("No se encontró la carpeta de esta canción."),
                QMessageBox.Icon.Warning,
            )
            return

        # Confirmar: sobrescribe cualquier ajuste hecho en el editor de sync.
        if (path / "lyrics.lrc").exists():
            reply = styled_message_box(
                self, tr("Sobrescribir letras"),
                tr('Se reemplazarán las letras actuales de "{artist} - {song}" '
                   "con las que devuelva la búsqueda.\n"
                   "Se perderán los ajustes de sincronización hechos a mano. ¿Continuar?"
                   ).format(artist=song_data['artist'], song=song_data['song']),
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        artist, song = song_data['artist'], song_data['song']
        self.begin_status(
            f"lyrics:{path}",
            tr("Buscando letras: {artist} - {song}...").format(artist=artist, song=song))

        def worker():
            found = False
            try:
                fetch_lyrics(artist, song, path)
                found = LYRICS_NOT_FOUND_TEXT not in (
                    path / "lyrics.lrc"
                ).read_text(encoding="utf-8")
            except Exception as e:
                logger.error("Error buscando letras de %s - %s: %s", artist, song, e)
            self.lyrics_refetched.emit(str(path), found)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_lyrics_refetched(self, path_str: str, found: bool):
        path = Path(path_str)
        # El parse cacheado apunta al .lrc viejo: invalidarlo o la canción
        # seguiría mostrando las letras anteriores.
        self.lazy_lyrics.cache.remove(f"lyrics_{path}")

        if (0 <= self.current_index < len(self.playlist)
                and Path(self.playlist[self.current_index]['path']) == path):
            if found:
                self._handle_lyrics_loaded(self.lazy_lyrics.load_lyrics_lazy(path))
            else:
                self.lyrics = []
                self._handle_lyrics_not_found()
            self.update_lyrics_menu_state()

        self.end_status(f"lyrics:{path}",
                        tr("Letras actualizadas") if found else tr("No se encontraron letras"))

    @staticmethod
    def _move_song_folder(old_path: Path, new_path: Path):
        """Mueve/combina la carpeta de la canción hacia new_path.

        Si new_path ya existe (misma canción re-corregida a un nombre que
        coincide con otra carpeta), combina archivo por archivo en vez de
        sobrescribir el directorio entero.
        """
        if not new_path.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            # shutil.move y no rename: soporta mover entre dispositivos
            # (librería en un disco externo, carpeta destino en otro).
            shutil.move(str(old_path), str(new_path))
        else:
            for entry in old_path.iterdir():
                dest = new_path / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, dest, dirs_exist_ok=True)
                    shutil.rmtree(entry)
                else:
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(entry), str(dest))
            old_path.rmdir()

        # Limpiar la carpeta de artista anterior si quedó vacía.
        old_artist_dir = old_path.parent
        if old_artist_dir != new_path.parent and old_artist_dir.is_dir() \
                and not any(old_artist_dir.iterdir()):
            old_artist_dir.rmdir()

    @staticmethod
    def _write_song_metadata(path: Path, artist: str, song: str) -> dict:
        """Reescribe data.json con el artista/canción nuevos.

        La metadata del archivo de origen (si la hay) se conserva tal cual:
        describe el archivo que se separó, no cómo se llame la carpeta.
        Devuelve el bloque de la canción ya escrito.
        """
        entry = {"path": str(path), "metadata": read_song_metadata(path)}
        (path / "data.json").write_text(
            json.dumps({artist: {song: entry}}, indent=4), encoding='utf-8'
        )
        return entry

    def _connect_dock_events(self):
        self.playlist_dock.visibilityChanged.connect(self._update_playlist_menu_state)

    def _connect_lazy_loading_signals(self):
        self.lazy_playlist.playlist_batch_updated.connect(self._on_songs_loaded)
        self.lazy_playlist.loading_finished.connect(self._on_playlist_loaded)
        self.cover_loaded.connect(self._handle_cover_loaded)
        self.lyrics_loaded.connect(self._handle_lyrics_loaded)
        self.lyrics_error.connect(self._handle_lyrics_error)
        self.lyrics_not_found.connect(self._handle_lyrics_not_found)
        self.lyrics_refetched.connect(self._handle_lyrics_refetched)

    # ──────────────────────────────────────────────────────────────────────
    # ── Timers ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _setup_timers(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        # Sin esto la "Hora" (y el conteo de caché) de la barra solo cambiaba
        # cuando algún evento llamaba update_status
        self.timer.timeout.connect(self.update_status)
        self.timer.start(1000)

        # update_display retorna temprano si no hay reproducción activa, y es
        # justo ahí donde el móvil necesita ver "Pausada"/"Detenido": timer
        # propio para el snapshot remoto (no hace nada si está apagado).
        self.remote_timer = QTimer(self)
        self.remote_timer.timeout.connect(self._publish_remote_state)
        self.remote_timer.start(1000)

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
        self._position_visualizer()

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
        elif key == Qt.Key.Key_F2:
            self._correct_selected()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Detener streams de audio y carga en curso antes del teardown:
        # streams vivos de PortAudio durante el cierre causan segfault
        self._control_channels('stop')
        self.lazy_playlist.stop_loading()
        self.demucs.cleanup()
        # Sin esto el hilo del servidor retiene el puerto hasta que muere el
        # proceso (en Windows, TIME_WAIT: el próximo arranque cae al 8771)
        self._stop_remote_mode()
        if self.playlist_dock.isVisible():
            self.playlist_dock.close()
        super().closeEvent(event)

    def center(self):
        screen = self.screen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    # ──────────────────────────────────────────────────────────────────────
    # ── Lazy loading callbacks ───────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _create_playlist_item(self, song_data: dict) -> QListWidgetItem:
        item = QListWidgetItem(f"{song_data['artist']} - {song_data['song']}")
        item.setIcon(self._audio_icon)
        item.setData(PlaylistItemDelegate.DURATION_ROLE, song_data.get('duration', ''))
        item.setData(PlaylistItemDelegate.PATH_ROLE, str(song_data.get('path', '')))
        return item

    def _on_songs_loaded(self, batch: list):
        self.playlist_widget.setUpdatesEnabled(False)
        try:
            for song_data in batch:
                key = (song_data['artist'], song_data['song'])
                if key in self._playlist_keys:
                    self._refresh_song_duration(key, song_data)
                    continue

                self._playlist_keys.add(key)
                self.playlist.append(song_data)
                self.playlist_widget.addItem(self._create_playlist_item(song_data))

                self._lyrics_fetch.put(
                    song_data['path'], song_data['artist'], song_data['song']
                )
        finally:
            self.playlist_widget.setUpdatesEnabled(True)

        # Una sola vez por lote: _on_songs_loaded se llama por lotes al escanear
        self._bump_playlist_rev()

        if self.playlist and not self.prev_btn.isEnabled():
            self._set_playback_buttons_enabled(True)

    def _refresh_song_duration(self, key: tuple[str, str], song_data: dict):
        """Completa la duración de una canción que entró a la playlist sin ella.

        DemucsWorker escribe data.json al inicio del proceso, mucho antes de
        los stems: un escaneo que caiga en esa ventana agrega la canción con
        duración vacía (get_song_duration lee separated/other.mp3, que aún no
        existe). El re-escaneo posterior sí trae la duración real, pero el
        dedupe por (artista, canción) la descartaba y el renglón se quedaba
        sin duración para siempre.
        """
        duration = song_data.get('duration', '')
        if not duration:
            return
        for row, existing in enumerate(self.playlist):
            if (existing['artist'], existing['song']) != key:
                continue
            if existing.get('duration'):
                return
            existing['duration'] = duration
            existing['has_separated'] = song_data.get('has_separated', True)
            item = self.playlist_widget.item(row)
            if item is not None:
                item.setData(PlaylistItemDelegate.DURATION_ROLE, duration)
            return

    def _on_playlist_loaded(self):
        self.end_status(
            "playlist",
            tr("Playlist cargada: {n} canciones").format(n=len(self.playlist)))
        self.update_status()

    def _handle_cover_loaded(self, image: QImage):
        self.cover_label.setPixmap(QPixmap.fromImage(image))

    def _handle_lyrics_loaded(self, lyrics_data: list):
        self.lyrics = lyrics_data or []
        self.update_lyrics_menu_state()

        if not (0 <= self.current_index < len(self.playlist)):
            return
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
        self.lyrics_current.setHtml(f'<center>{tr("Error")}: {error_msg}</center>')

    def _handle_lyrics_not_found(self):
        self.lyrics_current.setHtml(f'<center>{tr("No hay letras disponibles")}</center>')

    # ──────────────────────────────────────────────────────────────────────
    # ── Controles de reproducción ────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def play_current(self):
        self.stop_playback()
        if not (0 <= self.current_index < len(self.playlist)):
            return
        # Adelantar el destino al snapshot: cargar los stems bloquea el hilo
        # GUI y el móvil confirma su update optimista a los 250 ms. Sin esto
        # ese sondeo lee el estado viejo y el botón parpadea.
        self._publish_remote_target()
        if not self._setup_audio():
            self._publish_remote_state()
            return
        self._restore_mute_states()
        self._update_metadata()
        self._update_playback_ui('Activa')
        self.set_volume(self.volume)
        self.update_lyrics_menu_state()
        self.highlight_current_song()
        self._control_channels('play')
        self.tabs.setCurrentWidget(self.lyrics_container)

    def play_next(self):
        self.next_btn.setEnabled(False)
        self.stop_playback()
        if self.play_queue:
            # La cola tiene prioridad: se consume en orden (FIFO) antes de
            # seguir la playlist. Búsqueda por identidad porque la cola
            # guarda los mismos dicts de self.playlist, no índices.
            queued_song = self.play_queue.pop(0)
            self._refresh_queue_indicators()
            row = next(
                (i for i, s in enumerate(self.playlist) if s is queued_song), -1,
            )
            if row == -1:
                # Se eliminó de la playlist mientras esperaba en la cola.
                self.next_btn.setEnabled(True)
                self.play_next()
                return
            self.current_index = row
            self._apply_tag_mutes(queued_song)
        else:
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
        elif self.playback_state == "Detenido":
            # Tras Stop se limpiaron letras, portada y metadatos: arranque
            # completo en vez de solo reanudar los streams.
            self.play_current()
            return
        else:
            self._control_channels('unpause')
            self._update_playback_ui('Activa')
        self.update_lyrics_menu_state()

    def set_repeat(self, value: bool):
        """Fija el modelo y sincroniza el botón.

        Separado de toggle_repeat porque un comando remoto no pasa por el
        botón (puede llegar con la ventana minimizada).
        """
        self._repeat = bool(value)
        self.repeat_btn.setChecked(self._repeat)
        icon = "repeat_on" if self._repeat else "repeat"
        bg_image(self.repeat_btn, f"images/main_window/{icon}.png")

    def toggle_repeat(self):
        # El botón es checkable y ya cambió de estado: es la fuente aquí.
        self.set_repeat(self.repeat_btn.isChecked())

    # ──────────────────────────────────────────────────────────────────────
    # ── Letras en pantalla completa ──────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _toggle_lyrics_fullscreen(self):
        if self._lyrics_fullscreen:
            self._exit_lyrics_fullscreen()
        else:
            self._enter_lyrics_fullscreen()

    def _set_fs_viz_style(self, style: str):
        self._fs_viz_style = style
        if self._fs_visualizer is not None:
            self._fs_visualizer.set_style(style)
        # Sincronizar el check del menú (también cuando se cicla con V).
        for act in getattr(self, '_fs_viz_style_actions', []):
            act.setChecked(act.data() == style)

    def _cycle_fs_viz_style(self):
        styles = CircularVisualizerWidget.STYLES
        i = styles.index(self._fs_viz_style)
        self._set_fs_viz_style(styles[(i + 1) % len(styles)])

    def _position_fs_visualizer(self):
        if self._fs_visualizer is None:
            return
        w = self.lyrics_container.width()
        h = self.lyrics_container.height()
        side = int(min(w, h) * 0.85)
        # Un poco abajo del centro: el texto de la letra actual pesa arriba.
        y_offset = int(h * 0.09)
        self._fs_visualizer.setGeometry(
            (w - side) // 2, (h - side) // 2 + y_offset, side, side)
        self._fs_visualizer.lower()

    def _enter_lyrics_fullscreen(self):
        if self._lyrics_fullscreen:
            return
        self._lyrics_fullscreen = True
        self._lyrics_tab_index = self.tabs.indexOf(self.lyrics_container)
        # Tamaños para fullscreen: letra actual al máximo y la siguiente +8px
        # sobre su tamaño del QSS (fontInfo() no sirve: Qt no refleja la
        # fuente de un stylesheet en font()). Ambos se restauran al salir.
        self._fs_prev_font_size = self.lyrics_font_size
        m = re.search(r"#lyrics_next\s*\{[^}]*?font-size:\s*(\d+)px",
                      self.styleSheet())
        fs_next_px = (int(m.group(1)) if m else 24) + 8
        self.tabs.removeTab(self._lyrics_tab_index)
        self.lyrics_container.setParent(None)
        # Fuera de la ventana principal el contenedor deja de heredar su QSS
        # (estilos.css, con las fuentes/tamaños de las letras): re-aplicarlo,
        # más un fondo oscuro sólido porque como ventana independiente también
        # pierde el fondo del pane de las tabs.
        # Los QTextEdit van transparentes (la regla QWidget también los
        # matchea y taparían el visualizador circular que va detrás); el
        # fondo oscuro lo pone el contenedor.
        self.lyrics_container.setStyleSheet(
            self.styleSheet()
            + "\nQWidget { background-color: #14101c; }"
            + "\nQTextEdit { background: transparent; }"
            + "\nQTextEdit#lyrics_next { background: transparent; }"
            + f"\nQTextEdit#lyrics_next {{ font-size: {fs_next_px}px; }}"
        )
        self.lyrics_font_size = LYRICS_FONT_MAX
        self.apply_lyrics_font()
        # Visualizador circular: centrado, detrás del texto, alimentado por
        # el mismo AudioAnalyzer que las barras de la ventana principal.
        self._fs_visualizer = CircularVisualizerWidget(
            self.lyrics_container, style=self._fs_viz_style)
        self._position_fs_visualizer()
        self._fs_visualizer.show()
        self._fs_visualizer.lower()
        analyzer = getattr(self, 'analyzer', None)
        if analyzer is not None:
            analyzer.bars_ready.connect(self._fs_visualizer.set_bars)
        action = getattr(self, 'show_visualizer_action', None)
        if action is not None and not action.isChecked():
            self._fs_visualizer.hide()
        # Las QAction del menú tienen contexto de la ventana principal y no
        # disparan con esta ventana activa: replicar los atajos de letras
        # aquí, ligados a las mismas acciones (trigger respeta su enabled).
        # Se destruyen al salir para no duplicar los atajos en modo normal.
        self._fs_shortcuts = []
        for seq, action in (
            ("Ctrl+Shift+Up", self.increase_font_action),
            ("Ctrl+Shift+Down", self.decrease_font_action),
            ("Ctrl+Shift+Right", self.advance_action),
            ("Ctrl+Shift+Left", self.delay_action),
            ("Alt+1", self.track_toggle_actions[0]),
            ("Alt+2", self.track_toggle_actions[1]),
            ("Alt+3", self.track_toggle_actions[2]),
            ("Alt+4", self.track_toggle_actions[3]),
        ):
            sc = QShortcut(QKeySequence(seq), self.lyrics_container)
            sc.activated.connect(action.trigger)
            self._fs_shortcuts.append(sc)
        # V: cicla el estilo del visualizador circular en vivo.
        sc = QShortcut(QKeySequence("V"), self.lyrics_container)
        sc.activated.connect(self._cycle_fs_viz_style)
        self._fs_shortcuts.append(sc)
        # Espacio: pausa/reanuda sin salir del fullscreen. El atajo
        # intercepta antes de que el QTextEdit use la barra para scroll.
        sc = QShortcut(QKeySequence(Qt.Key.Key_Space), self.lyrics_container)
        sc.activated.connect(self.toggle_play_pause)
        self._fs_shortcuts.append(sc)
        self.lyrics_container.showFullScreen()
        self.lyrics_container.setFocus()

    def _exit_lyrics_fullscreen(self):
        if not self._lyrics_fullscreen:
            return
        self._lyrics_fullscreen = False
        for sc in self._fs_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._fs_shortcuts = []
        if self._fs_toast is not None:
            self._fs_toast_timer.stop()
            self._fs_toast.hide()
        if self._fs_visualizer is not None:
            analyzer = getattr(self, 'analyzer', None)
            if analyzer is not None:
                analyzer.bars_ready.disconnect(self._fs_visualizer.set_bars)
            self._fs_visualizer.deleteLater()
            self._fs_visualizer = None
        self.lyrics_container.setStyleSheet("")
        self.lyrics_font_size = self._fs_prev_font_size
        self.apply_lyrics_font()
        self.tabs.insertTab(
            self._lyrics_tab_index, self.lyrics_container, "Letras")
        self.tabs.setCurrentWidget(self.lyrics_container)

    def stop_playback(self):
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
        self._stream_pause_flag.set()

        if hasattr(self, '_writer_thread') and self._writer_thread is not None:
            self._writer_thread.join(timeout=2.0)
            self._writer_thread = None

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
        if not self._track_paths:
            return

        self._auto_unmute_gain = 0.0
        self._seek_position = start_frame
        sr = self._sr

        if hasattr(self, 'analyzer'):
            self.analyzer.configure(sr)
            self.analyzer.reset()

        cancel_flag = threading.Event()
        self._stream_cancel_flags = [cancel_flag]

        stream = sd.OutputStream(samplerate=sr, channels=self._channels, dtype='float32')
        stream.start()
        self._sd_streams = [stream]

        self._writer_thread = threading.Thread(
            target=self._stream_writer,
            args=(stream, list(self._track_paths), start_frame, cancel_flag),
            daemon=True,
        )
        self._writer_thread.start()

    def _stream_writer(self, stream, paths, start_frame, cancel_flag):
        """Hilo de audio: decodifica los stems por bloques y escribe la mezcla.

        Cada hilo abre sus propios archivos: el hilo GUI nunca toca estos
        decodificadores, solo cambia de canción o de posición parando este
        hilo y lanzando otro (_start_streams).
        """
        chunk_size = 1024
        pos = start_frame
        sr = self._sr
        files = []
        try:
            for path in paths:
                files.append(sf.SoundFile(str(path)))
                files[-1].seek(start_frame)

            while True:
                if cancel_flag.is_set():
                    break
                self._stream_pause_flag.wait()
                if cancel_flag.is_set():
                    break

                blocks = [f.read(chunk_size, dtype='float32', always_2d=True)
                          for f in files]
                # El header de los MP3 sobreestima la duración (~0.2-0.4 s): el
                # fin real de la canción es el primer bloque que llega corto
                n = min(len(b) for b in blocks)
                if n == 0:
                    break
                chunk = np.zeros((n, blocks[0].shape[1]), dtype='float32')
                vocal_ramp = self._auto_unmute_ramp(pos, n, sr)

                # Las pistas muteadas se leen igual: todos los archivos tienen
                # que avanzar juntos para seguir sincronizados
                for track, block in zip(TRACK_NAMES, blocks):
                    if self.mute_states[track]:
                        # Voz muteada: el auto-unmute puede reintroducirla con un
                        # fundido durante las líneas en blanco de la letra.
                        if track == "vocals" and vocal_ramp is not None:
                            base = self.individual_volumes[track] * (self.volume / 100.0)
                            chunk += block[:n] * base * vocal_ramp[:, None]
                        continue
                    vol = self.individual_volumes[track] * (self.volume / 100.0)
                    chunk += block[:n] * vol

                peak = np.max(np.abs(chunk))
                if peak > 1.0:
                    chunk /= peak

                if hasattr(self, 'analyzer'):
                    self.analyzer.process(chunk)

                try:
                    stream.write(chunk)
                except Exception:
                    break

                pos += n
                self._seek_position = pos
        except Exception as e:
            # Disco desconectado o stem ilegible a media canción (antes el audio
            # ya estaba entero en RAM): parar en limpio, sin avanzar de canción
            if not cancel_flag.is_set():
                logger.error("Error leyendo stems de %s: %s", paths[0].parent, e)
                QTimer.singleShot(0, self.stop_playback)
            return
        finally:
            for f in files:
                f.close()

        # Fin natural de canción
        if not cancel_flag.is_set():
            if self._repeat:
                QTimer.singleShot(0, self.play_current)
            else:
                QTimer.singleShot(0, self.play_next)

    def seek_to(self, target_ms: int):
        if self._seeking or not self._track_paths:
            return
        self._seeking = True
        try:
            max_ms = self.progress_song.maximum()
            target_ms = max(0, min(target_ms, max_ms - 1000))

            if target_ms >= max_ms - 1000:
                self._seeking = False
                self.play_next()
                return

            target_frame = int((target_ms / 1000.0) * self._sr)
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

    def _on_progress_moved(self, value_ms: int):
        # update_display esta congelado durante el arrastre, asi que la etiqueta
        # de tiempo la refresca el propio arrastre.
        if not self._track_paths:
            return
        total_s = self._total_frames // self._sr
        cur_m, cur_s = divmod(value_ms // 1000, 60)
        tot_m, tot_s = divmod(int(total_s), 60)
        self.progress_label.setText(
            f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}"
        )

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
                    self, tr("Error de Audio"),
                    tr("No se encontraron las pistas separadas para:\n{artist} - {song}"
                       ).format(artist=song['artist'], song=song['song']),
                    QMessageBox.Icon.Warning,
                )
                return False

            # Solo los headers (0.4 ms): el audio se decodifica por bloques en
            # _stream_writer. Decodificar aquí los 4 stems completos congelaba
            # la UI ~1 s y ocupaba ~270 MB por canción. Leer los 4 headers
            # conserva el aviso de stem corrupto al cargar.
            infos = [sf.info(str(p)) for p in track_paths]
            self._stop_streams()
            self._track_paths = list(track_paths)
            self._sr = infos[0].samplerate
            self._channels = infos[0].channels
            self._total_frames = min(i.frames for i in infos)
            self._seek_position = 0

            length_s = self._total_frames / self._sr
            length_ms = int(length_s * 1000)
            total_m, total_s = divmod(int(length_s), 60)
            self.progress_song.setRange(0, length_ms)
            self.progress_song.setValue(0)
            self.progress_label.setText(f"00:00 / {total_m:02d}:{total_s:02d}")
            return True

        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("Error cargando audio: {error}").format(error=e),
                QMessageBox.Icon.Critical,
            )
            return False

    # ──────────────────────────────────────────────────────────────────────
    # ── UI de reproducción ───────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _update_playback_ui(self, state: str):
        self.playback_state = state
        # Único lugar donde cambia playback_state: el móvil lo ve en su
        # siguiente poll sin esperar al timer del snapshot.
        self._publish_remote_state()
        if state != "Activa" and hasattr(self, 'visualizer'):
            self.visualizer.clear()
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
        item = self.playlist_widget.item(self.current_index)
        if item is None:
            return
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
        item.setForeground(QColor("black"))
        item.setBackground(QColor("#eea1cd"))
        self.playlist_widget.setCurrentItem(item)

    def clear_song_highlight(self):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if item is None:
                continue
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

    def set_track_volume(self, track_name: str, value: int):
        """Volumen de una pista, venga del slider o del móvil.

        Mueve el slider en vez de escribir `individual_volumes` a mano: así la
        ventana muestra lo que realmente está sonando y queda un solo camino
        (la señal del slider) hacia `set_individual_volume`.
        """
        if track_name not in TRACK_NAMES:
            return
        value = max(0, min(100, int(value)))
        slider = self._track_sliders.get(track_name)
        if slider is None:
            self.set_individual_volume(track_name, value)
        elif slider.value() != value:
            slider.setValue(value)
        else:
            self.set_individual_volume(track_name, value)

    def set_master_volume(self, value: int):
        """Volumen general. Mismo criterio que `set_track_volume`: el dial es
        la vista y `set_volume` el modelo."""
        value = max(0, min(100, int(value)))
        if self.volume_dial.value() != value:
            self.volume_dial.setValue(value)
        else:
            self.set_volume(value)

    def set_mute(self, track_name: str, muted: bool):
        """Fuente de verdad del mute: no depende de quién la llame.

        Mismo motivo que `set_repeat`: un comando remoto entra por una señal,
        no por un clic, así que `self.sender()` no sirve como entrada.
        """
        if track_name not in TRACK_NAMES:
            return
        self.mute_states[track_name] = bool(muted)
        btn = getattr(self, f"{track_name}_btn")
        icon_name = f"no_{track_name}" if muted else track_name
        btn.setIcon(QIcon(resource_path(f'images/main_window/icons01/{icon_name}.png')))
        btn.setChecked(bool(muted))
        if self._lyrics_fullscreen:
            self._show_fs_track_toast(track_name, bool(muted))

    # Nombres de pista tal como los escribe el usuario en las tags de la
    # cola (Administrar cola), normalizados (minúsculas, sin acentos) por
    # normalize_text antes de comparar contra esta tabla.
    _TAG_TRACK_ALIASES = {
        "bateria": "drums",
        "voz": "vocals", "vocal": "vocals", "vocales": "vocals",
        "bajo": "bass",
        "otros": "other", "otro": "other",
        # Sugerencias de la cola en inglés y portugués (bateria/voz ya valen)
        "drums": "drums", "vocals": "vocals", "bass": "bass", "other": "other",
        "baixo": "bass", "outros": "other", "outro": "other",
    }

    def _apply_tag_mutes(self, song_data: dict):
        """Al consumir una canción de la cola (no en el avance normal de la
        playlist), sus tags pueden nombrar pistas (Batería/Bajo/Voz/Otros):
        si encuentra alguna, mutea esas pistas y enciende el resto. Sin
        coincidencias no toca el mute actual."""
        found = {
            self._TAG_TRACK_ALIASES[key]
            for part in song_data.get('tags', '').split(',')
            if (key := normalize_text(part.strip())) in self._TAG_TRACK_ALIASES
        }
        if not found:
            return
        for track in TRACK_NAMES:
            self.set_mute(track, track in found)

    def toggle_mute(self):
        """Adaptador del clic: resuelve la pista y delega en `set_mute`."""
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        btn_to_track = {
            self.drums_btn: "drums", self.vocals_btn: "vocals",
            self.bass_btn: "bass", self.other_btn: "other",
        }
        track_name = btn_to_track.get(sender)
        if track_name:
            self.set_mute(track_name, not self.mute_states[track_name])

    _TRACK_LABELS = {"drums": N_("Batería"), "vocals": N_("Vocal"),
                     "bass": N_("Bajo"), "other": N_("Otros")}

    def _show_fs_track_toast(self, track_name: str, muted: bool):
        """Mensaje momentáneo (esquina superior derecha) al togglear una pista
        en fullscreen, donde los botones de mute no son visibles."""
        if self._fs_toast is None:
            self._fs_toast = QLabel(self.lyrics_container)
            self._fs_toast.setStyleSheet(
                "QLabel { background-color: rgba(20, 16, 28, 210); color: white; "
                "padding: 8px 14px; border-radius: 6px; font-size: 16px; }"
            )
            self._fs_toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._fs_toast_timer = QTimer(self)
            self._fs_toast_timer.setSingleShot(True)
            self._fs_toast_timer.timeout.connect(self._fs_toast.hide)
        label = tr(self._TRACK_LABELS.get(track_name, track_name))
        state = tr("Silenciada") if muted else tr("Activada")
        self._fs_toast.setText(f"{label}: {state}")
        self._fs_toast.adjustSize()
        margin = 24
        self._fs_toast.move(
            self.lyrics_container.width() - self._fs_toast.width() - margin, margin
        )
        self._fs_toast.show()
        self._fs_toast.raise_()
        self._fs_toast_timer.start(1500)

    # ──────────────────────────────────────────────────────────────────────
    # ── Auto-unmute de voz en secciones sin letra ────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    AUTO_UNMUTE_FADE_S = 0.5  # duración del fundido (segundos)
    _AUTO_UNMUTE_ROW_H = 24  # alto reservado para la fila del checkbox (px)

    def set_auto_unmute(self, value: bool):
        """Fuente de verdad del auto-unmute: mismo motivo que `set_repeat`,
        un comando remoto entra por señal y no por el click del checkbox."""
        value = bool(value)
        self.auto_unmute_enabled = value
        self.auto_unmute_check.setChecked(value)

    def _on_auto_unmute_toggled(self, checked: bool):
        self.auto_unmute_enabled = checked

    def _current_lyric_is_blank(self, current_time: float) -> bool:
        """True si la línea de letra activa en `current_time` dispara auto-unmute.

        Dispara cuando la línea está vacía (se guarda como `<center></center>`;
        al quitar las etiquetas no queda texto) o cuando tiene el color rojo
        (`AUTO_UNMUTE_COLOR`), que actúa como línea en blanco aunque tenga texto.
        Antes de la primera línea se considera que NO dispara (la voz sigue
        muteada en la intro).
        """
        if not self.lyrics:
            return False
        html = None
        for t, h in self.lyrics:
            if current_time >= t:
                html = h
            else:
                break
        if html is None:
            return False
        red_hex = LYRIC_COLORS[AUTO_UNMUTE_COLOR].lower()
        if f'color="{red_hex}"' in html.lower():
            return True
        text = re.sub(r'<[^>]*>', '', html).replace('&nbsp;', '').strip()
        return text == ''

    def _auto_unmute_ramp(self, pos: int, n: int, sr: int):
        """Devuelve una rampa de ganancia (n,) para la voz, o None.

        Interpola linealmente `self._auto_unmute_gain` hacia su objetivo
        (1.0 en líneas en blanco, 0.0 en el resto) a lo largo de
        `AUTO_UNMUTE_FADE_S` segundos. Devuelve None cuando la voz debe
        quedar totalmente muteada (sin aporte).
        """
        if self.auto_unmute_enabled and self.mute_states["vocals"]:
            target = 1.0 if self._current_lyric_is_blank(pos / sr) else 0.0
        elif self._auto_unmute_gain > 0.0:
            # Checkbox desactivado o voz desmuteada manualmente: fundir a 0
            target = 0.0
        else:
            self._auto_unmute_gain = 0.0
            return None

        fade_frames = max(1, int(self.AUTO_UNMUTE_FADE_S * sr))
        start_g = self._auto_unmute_gain
        step = n / fade_frames
        if target > start_g:
            end_g = min(target, start_g + step)
        else:
            end_g = max(target, start_g - step)

        ramp = np.linspace(start_g, end_g, n, dtype='float32')
        self._auto_unmute_gain = end_g
        if start_g <= 0.0 and end_g <= 0.0:
            return None
        return ramp

    # ──────────────────────────────────────────────────────────────────────
    # ── Actualización de display ─────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def update_display(self):
        if self.playback_state != "Activa" or not self._track_paths or self._seeking:
            return
        # Mientras el usuario arrastra el handle, escribir setValue lo devuelve
        # a la posicion de reproduccion: el arrastre se veia como cancelado
        # (y sliderReleased leia el valor viejo, no el soltado).
        if self.progress_song.isSliderDown():
            return
        try:
            sr = self._sr
            total_frames = self._total_frames

            if self._seek_position >= total_frames:
                # _stream_writer ya programa el avance al terminar la canción;
                # avanzar también aquí causaba doble play_next ocasional
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

    # playback_state es contrato con el móvil (queda en español): solo se
    # traduce el texto que se muestra.
    _STATE_LABELS = {"Activa": N_("Activa"), "Pausada": N_("Pausada"),
                     "Detenido": N_("Detenido")}

    def _state_text(self) -> str:
        return tr(self._STATE_LABELS.get(self.playback_state, self.playback_state))

    def update_status(self):
        if self._status_msg_timer.isActive():  # hay un show_status_message vigente
            return
        try:
            now = time.time()
            if now - self._last_stats_update > STATUS_CACHE_TTL:
                self._cached_stats = self.get_cache_stats()
                self._last_stats_update = now

            parts = [
                *self._status_ops.values(),
                tr("Canciones: {n}").format(n=len(self.playlist)),
                tr("Reproducción: {estado}").format(estado=self._state_text()),
                tr("Remoto: activo") if self._remote_server is not None else "",
                self.demucs.status_text(),
                tr("Cache: {n} elementos").format(
                    n=self._cached_stats.get('total_cached_items', 0)),
                tr("Fecha: {fecha}").format(
                    fecha=qlocale().toString(datetime.now(), 'dddd - dd/MM/yyyy')),
                tr("Hora: {hora}").format(hora=datetime.now().strftime('%H:%M')),
            ]
            self.status_label.setText(" | ".join(p for p in parts if p))
        except Exception:
            self.status_label.setText(
                tr("Canciones: {n}").format(n=len(self.playlist))
                + " | " + tr("Estado: {estado}").format(estado=self._state_text())
            )

    # ──────────────────────────────────────────────────────────────────────
    # ── Botones e init de controles ──────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def init_leds(self) -> QHBoxLayout:
        def _make_btn(name, size, icon, enabled):
            btn = QPushButton()
            btn.setObjectName(name)
            btn.setFixedSize(*size)
            btn.setEnabled(enabled)
            bg_image(btn, f"images/main_window/{icon}.png")
            return btn

        self.prev_btn = _make_btn('prev_btn', (40, 40), 'prev',False)
        self.play_btn = _make_btn('play_btn', (80, 80), 'play',False)
        self.next_btn = _make_btn('next_btn', (40, 40), 'next',False)
        self.stop_btn = _make_btn('stop_btn', (40, 40), 'stop',False)
        self.repeat_btn = _make_btn('repeat_btn', (40, 40), 'repeat',True)
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setChecked(False)


        self.volume_dial = CustomDial()
        self.volume_dial.setRange(0, 100)
        self.volume_dial.setValue(DEFAULT_VOLUME)
        self.volume_dial.setFixedSize(120, 120)
        self.volume_dial.setNotchesVisible(True)
        self.volume_dial.valueChanged.connect(self.set_volume)

        layout = QHBoxLayout()
        for w in (self.prev_btn, self.play_btn, self.next_btn,
                  self.repeat_btn, self.stop_btn, self.volume_dial):
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

            if track == "vocals":
                self.auto_unmute_check = QCheckBox("Auto-unmute")
                self.auto_unmute_check.setObjectName("auto_unmute_check")
                self.auto_unmute_check.setToolTip(
                    tr("Desmutea la voz en las secciones sin letra (con fundido)")
                )
                # Mismos assets de checkbox que el editor de letras (incluyen
                # la palomita); el estilizado custom perdía la marca al activar.
                unchecked = style_url('images/split_dialog/checkbox_unchecked.png')
                checked = style_url('images/split_dialog/checkbox_checked.png')
                hover = style_url('images/split_dialog/checkbox_hover01.png')
                hover_checked = style_url('images/split_dialog/checkbox_hover02.png')
                self.auto_unmute_check.setStyleSheet(f"""
                    QCheckBox {{ color: #cfcfe0; spacing: 8px; }}
                    QCheckBox::indicator {{ width: 18px; height: 18px; image: url({unchecked}); }}
                    QCheckBox::indicator:checked {{ image: url({checked}); }}
                    QCheckBox::indicator:unchecked:hover {{ image: url({hover}); }}
                    QCheckBox::indicator:checked:hover {{ image: url({hover_checked}); }}
                """)
                self.auto_unmute_check.setFixedHeight(self._AUTO_UNMUTE_ROW_H)
                self.auto_unmute_check.toggled.connect(self._on_auto_unmute_toggled)
                self.auto_unmute_check.setChecked(True)
                col.addWidget(self.auto_unmute_check)
            else:
                # Mismo alto reservado que el checkbox de la voz para que los
                # iconos/sliders de todas las columnas queden alineados.
                col.addSpacing(self._AUTO_UNMUTE_ROW_H)

            outer.addLayout(col)

        self.mute_buttons = list(self._track_buttons.values())
        self.enable_disable_buttons(False)
        return outer



    def setup_button(self, button: QPushButton, object_name: str, icon_name: str):
        button.setObjectName(object_name)
        button.setIconSize(QSize(120, 120))
        self._lazy_load_icon(button, icon_name, muted=False)
        button.setCheckable(True)
        button.clicked.connect(self.toggle_mute)

    def setup_slider(self, slider: QSlider, track_name: str):
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setFixedWidth(120)
        slider.valueChanged.connect(
            lambda v, t=track_name: self.set_individual_volume(t, v)
        )

    def _lazy_load_icon(self, btn: QPushButton, icon_name: str, muted: bool):
        name = f'no_{icon_name}' if muted else icon_name
        icon = self.lazy_images.load_icon_cached(
            resource_path(f'images/main_window/icons01/{name}.png'), (120, 120)
        )
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
    def load_folder(self, path: str | None = None):
        if not path:
            from os.path import expanduser
            path = QFileDialog.getExistingDirectory(
                self, tr("Seleccionar Carpeta"), expanduser("~/Music")
            )
        if not path:
            return
        # Carpeta nueva: items sin ordenar
        self._reset_sort_label()
        self.begin_status("playlist", tr("Cargando playlist..."))
        try:
            self.lazy_playlist.load_playlist_lazy(Path(path))
        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("Error iniciando carga: {error}").format(error=e),
                QMessageBox.Icon.Critical,
            )
            self.end_status("playlist", tr("Error cargando playlist"))

    def clear_playlist(self):
        self.stop_playback()
        self.playlist.clear()
        self._playlist_keys.clear()
        self.playlist_widget.clear()
        self.play_queue.clear()
        self.current_index = -1
        self._reset_sort_label()
        self._set_playback_buttons_enabled(False)
        self.stop_btn.setEnabled(False)
        self._bump_playlist_rev()
        self.update_status()

    def scan_folder(self, path: Path):
        """Escaneo síncrono de `path` (la biblioteca o la carpeta de una sola
        canción, como tras cada separación); agrega vía _on_songs_loaded (que
        ya maneja duplicados, icono, letras y botones)."""
        songs_found = []
        for json_file in path.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                dir_path = json_file.parent
                for artist, songs in data.items():
                    for song in songs:
                        songs_found.append({
                            "artist": artist,
                            "song": song,
                            "path": dir_path,
                            "duration": get_song_duration(dir_path),
                        })
            except Exception as e:
                styled_message_box(
                    self, tr("Error"),
                    tr("Error cargando {file}: {error}").format(file=json_file, error=e),
                    QMessageBox.Icon.Critical,
                )
        self._on_songs_loaded(songs_found)
        self.update_status()

    def remove_selected(self):
        # Recordar la canción actual por identidad: al borrar filas anteriores
        # los índices se corren y current_index dejaría de coincidir.
        current_song = (self.playlist[self.current_index]
                        if 0 <= self.current_index < len(self.playlist) else None)
        # Borrar de mayor a menor para que cada pop no recorra los índices
        # restantes que aún faltan por eliminar.
        rows = sorted(
            (self.playlist_widget.row(it)
             for it in self.playlist_widget.selectedItems()),
            reverse=True,
        )
        for row in rows:
            self.playlist_widget.takeItem(row)
            song = self.playlist.pop(row)
            self._playlist_keys.discard((song['artist'], song['song']))
        # Reubicar current_index a la misma canción; -1 si fue eliminada.
        if current_song is not None:
            self.current_index = next(
                (i for i, s in enumerate(self.playlist) if s is current_song), -1,
            )
        self._purge_queue()
        self._bump_playlist_rev()
        self.update_status()

    def sort_playlist(self, key: str = "artist", reverse: bool = False):
        """Ordena la playlist por artista, título o al azar ("random"),
        preserva la canción en reproducción y rehace los ítems del widget
        en el nuevo orden."""
        if not self.playlist:
            return

        # Sincronizar etiqueta y modo del toggle (también si se ordena por menú)
        for i, (k, r, label) in enumerate(self._SORT_MODES):
            if k == key and r == reverse:
                self._sort_mode = i
                self.sort_label.setText(tr(label))
                break

        # Recordar la canción en reproducción para restaurar su índice
        current_song = None
        if 0 <= self.current_index < len(self.playlist):
            current_song = self.playlist[self.current_index]

        if key == "random":
            random.shuffle(self.playlist)
        else:
            if key == "song":
                def sort_key(s):
                    return (s['song'].lower(), s['artist'].lower())
            else:
                def sort_key(s):
                    return (s['artist'].lower(), s['song'].lower())
            self.playlist.sort(key=sort_key, reverse=reverse)

        # Rehacer los ítems del widget en el nuevo orden
        self.playlist_widget.setUpdatesEnabled(False)
        try:
            self.playlist_widget.clear()
            for song_data in self.playlist:
                self.playlist_widget.addItem(self._create_playlist_item(song_data))
        finally:
            self.playlist_widget.setUpdatesEnabled(True)

        # Restaurar índice e iluminado de la canción en reproducción
        if current_song is not None:
            self.current_index = next(
                i for i, s in enumerate(self.playlist) if s is current_song
            )
            if self.playback_state in ("Activa", "Pausada"):
                self.highlight_current_song()

        self._bump_playlist_rev()
        self.update_status()

    def save_playlist_mlst(self):
        if not self.playlist:
            styled_message_box(
                self, tr("Playlist vacía"),
                tr("No hay canciones en la playlist para guardar."),
                QMessageBox.Icon.Information,
            )
            return
        file_path = self._prompt_mlst_path()
        if not file_path:
            return
        if self._write_mlst_file(self.playlist, file_path):
            self._current_mlst_path = file_path

    def export_queue_mlst(self):
        """Botón de exportar del diálogo "Administración de cola": vuelca las
        canciones actualmente encoladas (no toda la playlist) a un .mlst."""
        if not self.play_queue:
            styled_message_box(
                self, tr("Cola vacía"),
                tr("No hay canciones en la cola para exportar."),
                QMessageBox.Icon.Information,
            )
            return
        file_path = self._prompt_mlst_path()
        if not file_path:
            return
        self._write_mlst_file(self.play_queue, file_path)

    def _prompt_mlst_path(self) -> str:
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Guardar Playlist"),
            str(Path.home() / "Music"),
            "Music List (*.mlst)",
        )
        if not file_path:
            return ""
        if not file_path.endswith('.mlst'):
            file_path += '.mlst'
        return file_path

    def _write_mlst_file(self, songs: list[dict], file_path: str) -> bool:
        try:
            write_mlst(songs, file_path)
            styled_message_box(
                self, tr("Playlist guardada"),
                tr("Se guardaron {n} canciones en:\n{name}").format(
                    n=len(songs), name=Path(file_path).name),
            )
            return True
        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("No se pudo guardar: {error}").format(error=e),
                QMessageBox.Icon.Critical,
            )
            return False

    def load_playlist_mlst(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Cargar Playlist"),
            str(Path.home() / "Music"),
            "Music List (*.mlst)",
        )
        if not file_path:
            return

        try:
            name, songs = read_mlst(file_path)
            if not songs:
                styled_message_box(
                    self, tr("Playlist vacía"),
                    tr("El archivo no contiene canciones."),
                    QMessageBox.Icon.Warning,
                )
                return

            added = 0
            self.playlist_widget.setUpdatesEnabled(False)
            try:
                for song in songs:
                    artist, title, path = song["artist"], song["song"], song["path"]
                    if (artist, title) in self._playlist_keys:
                        continue

                    song_data = {
                        "artist": artist,
                        "song": title,
                        "path": Path(path),
                        "duration": get_song_duration(Path(path)),
                    }
                    self._playlist_keys.add((artist, title))
                    self.playlist.append(song_data)
                    self.playlist_widget.addItem(self._create_playlist_item(song_data))
                    self._lyrics_fetch.put(path, artist, title)
                    added += 1
            finally:
                self.playlist_widget.setUpdatesEnabled(True)

            if added and not self.prev_btn.isEnabled():
                self._set_playback_buttons_enabled(True)

            self._current_mlst_path = file_path
            if added:
                self._reset_sort_label()
                self._bump_playlist_rev()
            self.show_status_message(
                tr("Playlist cargada: {name} ({n} nuevas canciones)").format(
                    name=name, n=added)
            )
            self.update_status()

        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("No se pudo cargar: {error}").format(error=e),
                QMessageBox.Icon.Critical,
            )

    # ──────────────────────────────────────────────────────────────────────
    # ── Modo remoto (PlayIt Mobile) ──────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _bump_playlist_rev(self):
        """Marca la playlist como cambiada para que el móvil la re-descargue."""
        self._playlist_rev += 1
        self._publish_remote_playlist()

    def _publish_remote_playlist(self):
        if self._remote_bridge is None:
            return
        items = [{"i": i,
                  "artist": s.get("artist", ""),
                  "song": s.get("song", ""),
                  "duration": s.get("duration", "")}
                 for i, s in enumerate(self.playlist)]
        # Las carpetas van aparte: solo sirven para resolver /api/cover en el
        # hilo HTTP, nunca se le mandan al móvil.
        folders = [str(s.get("path", "")) for s in self.playlist]
        self._remote_bridge.publish_playlist(self._playlist_rev, items, folders)

    def _publish_remote_state(self, state: str | None = None,
                              position_ms: int | None = None,
                              duration_ms: int | None = None):
        """Snapshot para el móvil. `state` fuerza un valor distinto al real
        (ver `_publish_remote_target`)."""
        if self._remote_bridge is None:
            return
        song = (self.playlist[self.current_index]
                if 0 <= self.current_index < len(self.playlist) else {})
        pos_ms = dur_ms = 0
        if self._track_paths:
            pos_ms = int(self._seek_position / self._sr * 1000)
            dur_ms = int(self._total_frames / self._sr * 1000)
        queue = self._queue_indices()
        self._remote_bridge.publish_state({
            "v": 1,
            "state": state if state is not None else self.playback_state,
            "index": self.current_index,
            "artist": song.get("artist", ""),
            "song": song.get("song", ""),
            "position_ms": pos_ms if position_ms is None else position_ms,
            "duration_ms": dur_ms if duration_ms is None else duration_ms,
            "repeat": self._repeat,
            "count": len(self.playlist),
            "rev": self._playlist_rev,
            # Mezclador (PLAN_REMOTO §8): enteros 0-100, como los sliders.
            # Su sola presencia es lo que le dice al móvil que puede mostrar
            # los controles; un móvil viejo ignora las claves que no conoce.
            "master_volume": int(self.volume),
            "volumes": {t: int(round(self.individual_volumes[t] * 100))
                        for t in TRACK_NAMES},
            "mute": {t: bool(self.mute_states[t]) for t in TRACK_NAMES},
            "auto_unmute": bool(self.auto_unmute_enabled),
            # Cola remota: aditivo igual que el mezclador, no sube
            # PROTOCOL_VERSION. Índices de playlist (mismo "i" que
            # /api/playlist), en orden FIFO de consumo — no los dicts, que
            # nunca se serializan.
            "queue": queue,
            # Tags de las canciones encoladas, en el mismo orden que "queue"
            # (paralela, no un dict: las claves JSON serían strings y el
            # móvil tendría que reconvertirlas a índice). Son las que dispara
            # el auto-mute por tags al consumir la cola.
            "queue_tags": [
                str(self.playlist[i].get('tags', '') or '') for i in queue
            ],
        })

    def _queue_indices(self) -> list[int]:
        """`self.play_queue` traducida a índices de playlist, en orden FIFO.

        Búsqueda por identidad: play_queue guarda los mismos dicts de
        self.playlist, no índices. Una canción encolada que ya no está en la
        playlist (borrada mientras esperaba) no debería quedar, pero por las
        dudas se descarta acá en vez de mandarle un -1 al móvil.
        """
        indices = []
        for queued in self.play_queue:
            row = next((i for i, s in enumerate(self.playlist) if s is queued), -1)
            if row != -1:
                indices.append(row)
        return indices

    def set_song_tags(self, row: int, tags: str):
        """Tags de una canción de la playlist, vengan del administrador de
        cola o del móvil.

        Fuente de verdad separada de la vista, mismo motivo que `set_mute` /
        `set_repeat`: un comando remoto entra por señal y no puede leer la
        celda de tags del diálogo (que ni siquiera tiene por qué estar
        abierto).
        """
        if not isinstance(row, int) or isinstance(row, bool):
            return
        if not 0 <= row < len(self.playlist):
            return
        self.playlist[row]['tags'] = str(tags)
        self._refresh_queue_indicators()

    def _publish_remote_target(self):
        """Publica la canción que se está por cargar como si ya sonara.

        `play_current` bloquea el hilo GUI leyendo los stems; el móvil, que
        confirma su update optimista a los 250 ms, vería el estado anterior y
        revertiría el botón un instante. El tick de 1 s corrige si la carga
        termina fallando.
        """
        self._publish_remote_state(state="Activa", position_ms=0,
                                   duration_ms=0)

    def _handle_remote_command(self, cmd: str, arg):
        """Slot en el hilo GUI (la señal cruza desde el hilo HTTP)."""
        if cmd == "play_pause":
            self.toggle_play_pause()
        elif cmd == "stop":
            self.stop_playback()
        elif cmd == "next":
            if self.playlist:
                self.play_next()
        elif cmd == "prev":
            if self.playlist:
                self.play_previous()
        elif cmd == "repeat":
            self.set_repeat(not self._repeat if arg is None else bool(arg))
        elif cmd == "play_index":
            if isinstance(arg, int) and 0 <= arg < len(self.playlist):
                self.current_index = arg
                self.playlist_widget.setCurrentRow(arg)
                self.play_current()
        elif cmd == "set_mute":
            if isinstance(arg, tuple) and len(arg) == 2:
                self.set_mute(arg[0], bool(arg[1]))
        elif cmd == "set_volume":
            if isinstance(arg, tuple) and len(arg) == 2:
                self.set_track_volume(arg[0], arg[1])
        elif cmd == "set_master_volume":
            if isinstance(arg, int):
                self.set_master_volume(arg)
        elif cmd == "set_auto_unmute":
            self.set_auto_unmute(bool(arg))
        elif cmd == "queue_add":
            if isinstance(arg, int) and 0 <= arg < len(self.playlist):
                self._toggle_queue_many([self.playlist[arg]], True)
        elif cmd == "queue_remove":
            if isinstance(arg, int) and 0 <= arg < len(self.playlist):
                self._toggle_queue_many([self.playlist[arg]], False)
        elif cmd == "queue_clear":
            self.play_queue.clear()
            self._refresh_queue_indicators()
        elif cmd == "queue_reorder":
            self._remote_queue_reorder(arg)
        elif cmd == "queue_set_tags":
            if isinstance(arg, tuple) and len(arg) == 2:
                self.set_song_tags(arg[0], arg[1])
        self._publish_remote_state()

    def _remote_queue_reorder(self, order):
        """Aplica un reordenamiento remoto de la cola (índices de playlist).

        El servidor ya validó rango y que no haya repetidos; acá falta la
        única regla que no puede chequear con el playlist_count solo: que el
        pedido sea exactamente una permutación de la cola actual, ni una
        canción de más ni de menos. Si no calza se ignora entero en vez de
        aplicar a medias.
        """
        if not isinstance(order, list):
            return
        songs = [self.playlist[i] for i in order
                 if isinstance(i, int) and 0 <= i < len(self.playlist)]
        if len(songs) != len(self.play_queue):
            return
        if {id(s) for s in songs} != {id(s) for s in self.play_queue}:
            return
        self.play_queue[:] = songs
        self._refresh_queue_indicators()

    def toggle_remote_mode(self, enabled: bool):
        if not enabled:
            self._stop_remote_mode()
            self.update_status()
            return
        self._remote_bridge = RemoteBridge()
        self._remote_bridge.command.connect(self._handle_remote_command)
        self._remote_server = RemoteServer(self._remote_bridge)
        try:
            ip, port, token = self._remote_server.start()
        except RuntimeError as exc:
            self._remote_bridge = self._remote_server = None
            self.remote_action.setChecked(False)
            styled_message_box(
                self, tr("Modo remoto"), tr("No se pudo abrir el puerto:\n{error}").format(error=exc),
                QMessageBox.Icon.Critical,
            )
            return
        self._publish_remote_playlist()
        self._publish_remote_state()
        self.update_status()
        self._show_pair_dialog(ip, port, token)

    def _show_pair_dialog(self, ip: str, port: int, token: str):
        dialog = RemotePairDialog(self, ip=ip, port=port, token=token,
                                  name=self._remote_bridge.name)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.regenerate_requested.connect(
            lambda: self._regenerate_remote_token(dialog)
        )
        # El QR ya cumplió su función cuando el teléfono se empareja: la señal
        # llega desde el hilo HTTP y Qt entrega el slot en el hilo GUI.
        bridge = self._remote_bridge
        bridge.paired.connect(dialog.on_paired)
        try:
            dialog.exec()
        finally:
            # El diálogo muere al salir de acá; sin esto la señal seguiría
            # apuntando a un objeto destruido en el próximo emparejamiento.
            bridge.paired.disconnect(dialog.on_paired)
        if dialog.paired_with:
            self.show_status_message(
                tr("PlayIt Mobile conectado desde {host}").format(host=dialog.paired_with))

    def _regenerate_remote_token(self, dialog):
        """Reinicia el servidor con otro token: desempareja lo ya conectado."""
        if self._remote_server is None:
            return
        self._remote_server.stop()
        try:
            ip, port, token = self._remote_server.start(rotate=True)
        except RuntimeError as exc:
            self._remote_bridge = self._remote_server = None
            self.remote_action.setChecked(False)
            self.update_status()
            dialog.reject()
            styled_message_box(
                self, tr("Modo remoto"), tr("No se pudo abrir el puerto:\n{error}").format(error=exc),
                QMessageBox.Icon.Critical,
            )
            return
        dialog.set_pairing(ip, port, token, self._remote_bridge.name)

    def _stop_remote_mode(self):
        if self._remote_server is not None:
            self._remote_server.stop()
        self._remote_server = None
        self._remote_bridge = None

    # ──────────────────────────────────────────────────────────────────────
    # ── Letras ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def update_lyrics_display(self):
        if not self.lyrics or self.playback_state != "Activa":
            return
        # Posición real de reproducción (frames escritos), no el slider:
        # el slider solo se refresca cada 1 s (self.timer), lo que provocaba
        # hasta ~1 s de retraso respecto al editor de sincronización.
        if self._track_paths:
            current_time = self._seek_position / self._sr
        else:
            current_time = self.progress_song.value() / 1000.0
        current_html = next_html = ""
        for i, (t, html) in enumerate(self.lyrics):
            if current_time >= t:
                current_html = html
                next_html = self.lyrics[i + 1][1] if i + 1 < len(self.lyrics) else ""
            else:
                break
        # Los bloques multilínea del .lrc (líneas de continuación) llegan con
        # '\n', que setHtml colapsa en un espacio: convertir a <br> al
        # renderizar para que el salto de línea sí se muestre.
        # El placeholder en disco queda en español (needs_lyrics lo busca);
        # solo se traduce lo que se muestra.
        current_html = current_html.replace(LYRICS_NOT_FOUND_TEXT, tr("Letras no encontradas"))
        current_html = current_html.replace('\n', '<br>')
        next_html = next_html.replace('\n', '<br>')
        self.lyrics_current.setHtml(current_html)
        self.lyrics_next.setHtml(f'<center>{next_html}</center>')
        # Altura según contenido: con la altura fija mínima, una línea de dos
        # renglones (<br>) dejaba el segundo cortado. Sin textWidth el
        # documento no calcula layout y size() devuelve 0.
        doc = self.lyrics_next.document()
        viewport = self.lyrics_next.viewport()
        if viewport is not None:
            doc.setTextWidth(viewport.width())
        doc_h = int(doc.size().height())
        self.lyrics_next.setFixedHeight(max(LYRICS_NEXT_MIN_HEIGHT, doc_h + 8))

    def update_lyrics_menu_state(self):
        enabled = (
            self.playback_state == "Activa"
            and self.current_index != -1
            and not self._lyrics_has_error()
        )
        self.advance_action.setEnabled(enabled)
        self.delay_action.setEnabled(enabled)
        if hasattr(self, 'sync_editor_action'):
            # El editor trabaja sobre los archivos en disco: no depende del
            # estado de reproducción, solo de que existan vocals + .lrc.
            self.sync_editor_action.setEnabled(self._has_sync_assets())

    def _lyrics_has_error(self) -> bool:
        if not self.lyrics or not isinstance(self.lyrics, list):
            return True
        error_keywords = ("no se encontraron", "letras no encontradas")
        return any(
            any(kw in html.lower() for kw in error_keywords)
            for _, html in self.lyrics
        )

    def _has_sync_assets(self) -> bool:
        """True si la canción actual tiene vocals.mp3 + lyrics.lrc.

        Los stems viven en <path>/separated/; el .lrc en la raíz <path>.
        """
        if not (0 <= self.current_index < len(self.playlist)):
            return False
        path = Path(self.playlist[self.current_index]["path"])
        vocals = path / "separated" / "vocals.mp3"
        return vocals.exists() and (path / "lyrics.lrc").exists()

    def open_lyrics_sync_editor(self):
        """Abre el editor de sincronización por onda (ventana aparte).

        Pausa el audio principal antes de abrir; el diálogo es modal, así
        que la ventana principal queda bloqueada mientras se edita.
        """
        if not self._has_sync_assets():
            return
        path = Path(self.playlist[self.current_index]["path"])

        # Pausar reproducción principal para no solapar audio.
        if self.playback_state == "Activa":
            self._control_channels('pause')
            self._update_playback_ui('Pausada')

        dialog = LyricsSyncDialog(
            self, path / "separated" / "vocals.mp3", path / "lyrics.lrc",
        )
        # El editor usa Ctrl+F (enfocar su buscador), Ctrl+D (separar línea) y
        # Ctrl+Shift+←/→ (extender selección de registros): deshabilitar las
        # acciones globales con esos atajos (pantalla completa de letras,
        # dividir, avanzar/retrasar timing) y la búsqueda global, para que no
        # se disparen encima del editor.
        split_was_enabled = self.split_action.isEnabled()
        self.search_action.setEnabled(False)
        self.split_action.setEnabled(False)
        self.lyrics_fullscreen_action.setEnabled(False)
        self.advance_action.setEnabled(False)
        self.delay_action.setEnabled(False)
        try:
            dialog.exec()
        finally:
            self.search_action.setEnabled(True)
            self.split_action.setEnabled(split_was_enabled)
            self.lyrics_fullscreen_action.setEnabled(True)
            self.advance_action.setEnabled(True)
            self.delay_action.setEnabled(True)

        if dialog.saved:
            # Invalidar cache y recargar letras editadas.
            self.lazy_lyrics.cache.remove(f"lyrics_{path}")
            self._handle_lyrics_loaded(self.lazy_lyrics.load_lyrics_lazy(path))
        self.update_lyrics_menu_state()

    def adjust_lyrics_timing(self, offset: float):
        try:
            path = Path(self.playlist[self.current_index]["path"])
            lrc_path = path / "lyrics.lrc"
            with open(lrc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            modified = self._process_lines(lines, offset)
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.writelines(modified)
            # Invalidar el parse cacheado: sin esto, al volver a la canción
            # se mostraría la versión vieja de las letras
            self.lazy_lyrics.cache.remove(f"lyrics_{path}")
            self._handle_lyrics_loaded(self.lazy_lyrics.load_lyrics_lazy(path))
        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("No se pudo ajustar: {error}").format(error=e),
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
        # Aritmética entera en centisegundos: evita errores de redondeo
        # de float (p.ej. 01:59.80 + 0.5 daba 02:00.29)
        mins, rest = time_str.split(':', 1)
        secs, centis = rest.split('.', 1)
        total_cs = max(
            0,
            int(mins) * 6000 + int(secs) * 100 + int(centis)
            + round(offset * 100),
        )
        m, rem = divmod(total_cs, 6000)
        s, c = divmod(rem, 100)
        return f"{m:02d}:{s:02d}.{c:02d}"

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
        # setStyleSheet REEMPLAZA la hoja del widget: conservar el fondo
        # transparente y sin borde con los que se creó, o el marco default
        # del QTextEdit se vuelve visible tras cambiar la fuente (p. ej. al
        # entrar/salir del fullscreen de letras).
        self.lyrics_current.setStyleSheet(
            f"QTextEdit {{ font-size: {self.lyrics_font_size}px;"
            " background: transparent; border: none; }"
        )

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
                    logger.error("Error cargando portada: %s", e)

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
            logger.error("Error actualizando metadatos: %s", e)

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
                logger.error("Error en precarga: %s", e)

        threading.Thread(target=worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # ── Demucs ───────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def show_split_dialog(self):
        if not self.deps.demucs_available:
            styled_message_box(
                self, tr("Funcionalidad no disponible"),
                tr("La separación de pistas requiere Demucs, pero no está instalado.\n\n"
                   "Puede instalar Demucs y demás dependencias desde las opciones del menú."),
                QMessageBox.Icon.Warning,
            )
            return
        self.split_dialog = SplitDialog(self)
        bg_image(self.split_dialog, 'images/split_dialog/split.png')
        self.split_dialog.process_started.connect(self.demucs.add)
        self.split_dialog.batch_started.connect(self.demucs.add_batch)
        self.split_dialog.show()

    # ──────────────────────────────────────────────────────────────────────
    # ── Workers en QThread ───────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def _start_worker_thread(self, worker, thread_attr: str, worker_attr: str,
                             on_finished, on_error, status_msg: str):
        setattr(self, thread_attr, start_worker_thread(worker, on_finished, on_error))
        setattr(self, worker_attr, worker)
        # Clave = thread_attr: los handlers de fin cierran con end_status(thread_attr, …)
        self.begin_status(thread_attr, status_msg)

    # ──────────────────────────────────────────────────────────────────────
    # ── Descarga MP3 ─────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def download_mp3(self):
        if not self.deps.ytdlp_available:
            styled_message_box(
                self, tr("yt-dlp no instalado"),
                tr("Debe instalar yt-dlp primero desde Opciones > Dependencias."),
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
            tr("Descargando MP3..."),
        )

    def _on_download_finished(self, message: str):
        self.end_status('download_thread', tr("Descarga completada."))
        styled_message_box(self, tr("Descarga finalizada"), message, QMessageBox.Icon.Information)

    def _on_download_error(self, msg: str):
        self.end_status('download_thread', tr("Error en descarga."))
        styled_message_box(self, tr("Error de descarga"), msg, QMessageBox.Icon.Critical)

    # ──────────────────────────────────────────────────────────────────────
    # ── Menú ─────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _submenu(parent, title: str) -> QMenu:
        # El assert descarta el "| None" de los stubs de PyQt6: en un
        # QMainWindow estos menús siempre se crean
        menu = parent.addMenu(title)
        assert menu is not None
        return menu

    def _add_action(self, menu: QMenu, label: str, slot=None, shortcut: str = "", *,
                    checkable: bool = False, checked: bool = False,
                    enabled: bool = True) -> QAction:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(shortcut)
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
        if slot:
            action.triggered.connect(slot)
        action.setEnabled(enabled)
        menu.addAction(action)
        return action

    def _set_language(self, code: str):
        if code == current_language():
            return
        save_setting("language", code)
        styled_message_box(
            self, tr("Idioma"),
            tr("El idioma se aplicará al reiniciar PlayIt."))

    def init_menu(self):
        bar = self.menuBar()
        assert bar is not None
        file_menu = self._submenu(bar, tr("Archivo"))
        options_menu = self._submenu(bar, tr("Opciones"))
        help_menu = self._submenu(bar, tr("Ayuda"))
        add = self._add_action

        # Archivo
        add(file_menu, tr("Seleccionar Carpeta"), self.load_folder, "Ctrl+O")
        playlist_menu = self._submenu(file_menu, tr("Playlists"))
        add(playlist_menu, tr("Cargar playlist..."), self.load_playlist_mlst)
        add(playlist_menu, tr("Guardar playlist como..."), self.save_playlist_mlst)
        file_menu.addSeparator()
        self.split_action = add(file_menu, tr("Dividir..."), self.show_split_dialog, "Ctrl+D")
        file_menu.addSeparator()
        add(file_menu, tr("Remover de PlayList"), self.remove_selected)
        add(file_menu, tr("Limpiar Playlist"), self.clear_playlist)
        sort_menu = self._submenu(file_menu, tr("Ordenar Playlist"))
        for key, reverse, label in self._SORT_MODES:
            add(sort_menu, tr(label),
                lambda _=False, k=key, r=reverse: self.sort_playlist(k, reverse=r))
        file_menu.addSeparator()
        add(file_menu, tr("&Salir"), self.close_application, "Ctrl+Q")

        # Opciones
        self.show_playlist_action = add(
            options_menu, tr("Mostrar lista"), self._toggle_playlist_visibility,
            checkable=True, checked=True)
        self.show_visualizer_action = add(
            options_menu, tr("Visualizador de audio"), self._toggle_visualizer,
            checkable=True, checked=True)

        # Estilo del visualizador circular del fullscreen de letras
        # (también se cicla con V dentro del fullscreen).
        fs_viz_menu = self._submenu(options_menu, tr("Visualizador en pantalla completa"))
        self._fs_viz_style_actions = []
        for key, label in (("bars", tr("Barras circulares")),
                           ("wave", tr("Onda")),
                           ("electric", tr("Electricidad")),
                           ("hbars", tr("Barras horizontales")),
                           ("none", tr("Ninguno"))):
            act = add(fs_viz_menu, label, lambda _=False, k=key: self._set_fs_viz_style(k),
                      checkable=True, checked=key == self._fs_viz_style)
            act.setData(key)
            self._fs_viz_style_actions.append(act)

        self.search_action = add(options_menu, tr("Buscar canción..."),
                                 self.show_search_dialog, "Ctrl+Shift+F")
        self.lyrics_fullscreen_action = add(options_menu, tr("Letras en pantalla completa"),
                                            self._enter_lyrics_fullscreen, "Ctrl+F")

        lyrics_menu = self._submenu(options_menu, tr("Modificar Lyrics"))
        self.advance_action = add(lyrics_menu, tr(">> Mostrar Después 0.5s"),
                                  lambda: self.adjust_lyrics_timing(0.5),
                                  "Ctrl+Shift+Right", enabled=False)
        self.delay_action = add(lyrics_menu, tr("<< Mostrar Antes 0.5s"),
                                lambda: self.adjust_lyrics_timing(-0.5),
                                "Ctrl+Shift+Left", enabled=False)
        lyrics_menu.addSeparator()
        self.increase_font_action = add(lyrics_menu, tr("Incrementar tamaño"),
                                        self.increase_lyrics_font, "Ctrl+Shift+Up")
        self.decrease_font_action = add(lyrics_menu, tr("Disminuir tamaño"),
                                        self.decrease_lyrics_font, "Ctrl+Shift+Down")
        lyrics_menu.addSeparator()
        self.sync_editor_action = add(lyrics_menu, tr("Editor de sincronización (onda)…"),
                                      self.open_lyrics_sync_editor, "Ctrl+Shift+E",
                                      enabled=False)

        tracks_menu = self._submenu(options_menu, tr("Pistas"))
        self.track_toggle_actions = [
            add(tracks_menu, label, btn.click, shortcut)
            for label, shortcut, btn in (
                (tr("Batería (mute/unmute)"), "Alt+1", self.drums_btn),
                (tr("Vocal (mute/unmute)"), "Alt+2", self.vocals_btn),
                (tr("Bajo (mute/unmute)"), "Alt+3", self.bass_btn),
                (tr("Otros (mute/unmute)"), "Alt+4", self.other_btn),
            )
        ]

        self.remote_action = add(options_menu, tr("Modo remoto (PlayIt Mobile)…"),
                                 checkable=True)
        self.remote_action.toggled.connect(self.toggle_remote_mode)
        add(options_menu, tr("Limpiar Cache"), self.cleanup_resources_manual)

        # Idioma: se guarda y aplica al reiniciar (la UI se construye una vez)
        lang_menu = self._submenu(options_menu, tr("Idioma"))
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        for code, name in SUPPORTED.items():
            act = add(lang_menu, name, lambda _=False, c=code: self._set_language(c),
                      checkable=True, checked=code == current_language())
            lang_group.addAction(act)

        # Dependencias: Visual C++ solo en Windows; CUDA no existe en macOS
        # (Demucs usa MPS automáticamente ahí)
        deps_menu = self._submenu(options_menu, tr("Dependencias"))
        self.install_python_action = add(deps_menu, tr("Instalar Python"),
                                         self.deps.install_python)
        if IS_WINDOWS:
            self.install_vc_action = add(deps_menu, tr("Instalar Visual C++"),
                                         self.deps.install_vc)
        self.install_ffmpeg_action = add(deps_menu, tr("Instalar FFmpeg"),
                                         self.deps.install_ffmpeg)
        self.install_demucs_action = add(deps_menu, tr("Instalar Demucs"),
                                         self.deps.install_demucs)
        if not IS_MAC:
            self.install_cuda_action = add(deps_menu, tr("Instalar CUDA (GPU Nvidia necesario)"),
                                           self.deps.install_cuda)
        deps_menu.addSeparator()
        self.install_ytdlp_action = add(deps_menu, tr("Instalar YT-DLP (Youtube → MP3)"),
                                        self.deps.install_ytdlp)
        options_menu.addSeparator()
        self.download_mp3_action = add(options_menu, tr("Descargar MP3..."), self.download_mp3)
        # Estado inicial (flags por defecto); `deps.changed` lo refresca
        # cuando termina el chequeo en segundo plano
        self._update_dependency_menus()

        # Ayuda
        add(help_menu, tr("Sobre Playit"), self.show_about_dialog)
        add(help_menu, tr("Mostrar Queue"), self.show_queue_dialog)
        self.check_updates_action = add(help_menu, tr("Buscar actualizaciones..."),
                                        self.check_for_updates)

    # ──────────────────────────────────────────────────────────────────────
    # ── Actualizaciones de menú ──────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
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
        # Mientras corre, update_status no pisa el mensaje puntual; al vencer
        # repinta el resumen.
        self._status_msg_timer = QTimer(self)
        self._status_msg_timer.setSingleShot(True)
        self._status_msg_timer.timeout.connect(self.update_status)
        # Operaciones en curso {clave: texto}: encabezan el resumen hasta que
        # terminan (begin_status / end_status)
        self._status_ops: dict[str, str] = {}
        self.deps.op_started.connect(self.begin_status)
        self.deps.op_finished.connect(self.end_status)
        self.status_bar.showMessage(tr("Listo"), 3000)
        self.update_status()

    def show_status_message(self, text: str, ms: int = 5000):
        """Mensaje puntual en la barra de estado, visible `ms` aunque llegue
        un update_status. No sirve QStatusBar.showMessage: status_label es
        permanente con stretch=1 y deja sin ancho el área del mensaje."""
        self.status_label.setText(text)
        self._status_msg_timer.start(ms)

    def begin_status(self, key: str, text: str):
        """Operación larga en curso: su texto encabeza el resumen de la barra
        hasta end_status, sin taparlo (siguen viéndose el progreso de Demucs,
        la hora y otras operaciones simultáneas)."""
        self._status_ops[key] = text
        self.update_status()

    def end_status(self, key: str, text: str):
        """Cierra la operación `key` y muestra su resultado como mensaje puntual."""
        self._status_ops.pop(key, None)
        self.show_status_message(text)

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
                self, tr("Limpieza Completa"),
                tr("Cache limpiado exitosamente.\n"
                   "Elementos eliminados: {n}\n"
                   "Memoria liberada aproximada: {mb:.1f}MB"
                   ).format(n=freed, mb=freed * 2),
            )
        except Exception as e:
            styled_message_box(
                self, tr("Error"), tr("Error durante la limpieza: {error}").format(error=e),
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
    # ── Buscar actualizaciones ───────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_version(version: str) -> tuple:
        parts = []
        for chunk in version.split('.'):
            digits = ''.join(c for c in chunk if c.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    def check_for_updates(self):
        self.check_updates_action.setEnabled(False)
        self._start_worker_thread(
            UpdateCheckWorker(), 'update_check_thread', 'update_check_worker',
            self._on_update_check_success,
            self._on_update_check_error,
            tr("Buscando actualizaciones..."),
        )

    def _show_update_dialog(self, message: str, show_cancel: bool = False) -> int:
        dialog = UpdateDialog(self, message, show_cancel)
        bg_image(dialog, 'images/split_dialog/split.png')
        return dialog.exec()

    def _on_update_check_success(self, latest_version: str, html_url: str):
        self.check_updates_action.setEnabled(True)
        self.end_status('update_check_thread', tr("Búsqueda de actualizaciones completa."))

        if __version__ == "dev":
            self._show_update_dialog(
                tr("Estás usando una build de desarrollo.\n"
                   "Última versión publicada: {version}").format(version=latest_version)
            )
            return

        if self._parse_version(latest_version) > self._parse_version(__version__):
            respuesta = self._show_update_dialog(
                tr("Hay una nueva versión disponible: {latest}\n"
                   "Versión actual: {current}\n\n"
                   "¿Abrir la página de descarga?"
                   ).format(latest=latest_version, current=__version__),
                show_cancel=True,
            )
            if respuesta == QDialog.DialogCode.Accepted and html_url:
                QDesktopServices.openUrl(QUrl(html_url))
        else:
            self._show_update_dialog(
                tr("Ya tienes la última versión instalada ({version}).").format(version=__version__))

    def _on_update_check_error(self, msg: str):
        self.check_updates_action.setEnabled(True)
        self.end_status('update_check_thread', tr("Error buscando actualizaciones."))
        self._show_update_dialog(msg)

    def show_search_dialog(self):
        self._search_query = ""
        self._search_matches = []
        self._search_pos = -1
        dialog = SearchDialog(self)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.search_requested.connect(self._search_playlist)
        dialog.exec()
        # Foco a la playlist al cerrar: Enter reproduce la canción seleccionada
        if self._search_matches:
            self.playlist_widget.setFocus()

    def _search_playlist(self, text: str):
        query = normalize_text(text)
        if query != self._search_query:
            self._search_query = query
            self._search_matches = [
                i for i, t in enumerate(self.playlist)
                if query in normalize_text(f"{t['artist']} - {t['song']}")
            ]
            self._search_pos = -1

        if not self._search_matches:
            self.show_status_message(tr("Sin coincidencias para: {text}").format(text=text))
            return

        self._search_pos = (self._search_pos + 1) % len(self._search_matches)
        row = self._search_matches[self._search_pos]
        self.playlist_widget.setCurrentRow(row)
        self.playlist_widget.scrollToItem(
            self.playlist_widget.item(row),
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        song = self.playlist[row]
        self.show_status_message(
            tr("Coincidencia {pos}/{total}: {artist} - {song}").format(
                pos=self._search_pos + 1, total=len(self._search_matches),
                artist=song['artist'], song=song['song'])
        )

    # ──────────────────────────────────────────────────────────────────────
    # ── Utilidades ───────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    def close_application(self):
        app = QApplication.instance()
        if app is not None:
            app.quit()
