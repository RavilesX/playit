import weakref
from pathlib import Path
from typing import Dict, Optional, Any, Callable
from functools import lru_cache
import threading
import time
import json
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, Qt
from PyQt6.QtGui import QPixmap, QIcon
import pygame
from PIL import Image
import io
from mutagen.mp3 import MP3


class ResourceCache:
    """Cache inteligente con lazy loading y gestión automática de memoria"""

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._cache: Dict[str, Any] = {}
        self._access_times: Dict[str, float] = {}
        self._loading_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.RLock()

    def get(self, key: str, loader: Callable[[], Any]) -> Any:
        """Obtiene un recurso del cache o lo carga usando lazy loading"""
        with self._lock:
            # Si está en cache, actualizar tiempo de acceso y retornar
            if key in self._cache:
                self._access_times[key] = time.time()
                return self._cache[key]

            # Crear lock para este recurso si no existe
            if key not in self._loading_locks:
                self._loading_locks[key] = threading.Lock()

        # Cargar el recurso (fuera del lock principal para evitar bloqueos)
        with self._loading_locks[key]:
            # Verificar nuevamente por si otro hilo ya lo cargó
            with self._lock:
                if key in self._cache:
                    self._access_times[key] = time.time()
                    return self._cache[key]

            # Cargar el recurso
            try:
                resource = loader()
                with self._lock:
                    self._cache[key] = resource
                    self._access_times[key] = time.time()
                    self._cleanup_if_needed()
                return resource
            except Exception as e:
                print(f"Error cargando recurso {key}: {e}")
                return None

    def _cleanup_if_needed(self):
        """Limpia el cache si excede el tamaño máximo (LRU)"""
        if len(self._cache) <= self.max_size:
            return

        # Encontrar el elemento menos recientemente usado
        oldest_key = min(self._access_times.keys(),
                         key=lambda k: self._access_times[k])

        del self._cache[oldest_key]
        del self._access_times[oldest_key]
        if oldest_key in self._loading_locks:
            del self._loading_locks[oldest_key]

    def clear(self):
        """Limpia completamente el cache"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self._loading_locks.clear()

    def remove(self, key: str):
        """Elimina un elemento específico del cache"""
        with self._lock:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)
            self._loading_locks.pop(key, None)


class LazyAudioManager:
    """Gestor de audio con carga perezosa"""

    def __init__(self):
        self.cache = ResourceCache(max_size=20)  # Máximo 20 canciones en memoria
        self.preload_thread = None
        self.current_sounds = []
        self.current_channels = []

    def load_audio_lazy(self, path: Path) -> Optional[list]:
        """Carga audio de forma perezosa"""
        cache_key = f"audio_{path}"

        def loader():
            try:
                sounds = []
                for track in ["drums", "vocals", "bass", "other"]:
                    track_path = path / "separated" / f"{track}.mp3"
                    if track_path.exists():
                        sound = pygame.mixer.Sound(str(track_path))
                        sounds.append(sound)
                    else:
                        raise FileNotFoundError(f"Track not found: {track_path}")
                return sounds
            except Exception as e:
                print(f"Error loading audio from {path}: {e}")
                return None

        return self.cache.get(cache_key, loader)

    def preload_next_songs(self, playlist: list, current_index: int, count: int = 2):
        """Precarga las siguientes canciones en un hilo separado"""
        if self.preload_thread and self.preload_thread.is_alive():
            return

        def preload_worker():
            for i in range(1, count + 1):
                next_index = (current_index + i) % len(playlist)
                if next_index < len(playlist):
                    song_path = playlist[next_index]["path"]
                    self.load_audio_lazy(song_path)  # Esto cargará en cache

        self.preload_thread = threading.Thread(target=preload_worker, daemon=True)
        self.preload_thread.start()

    def cleanup_old_audio(self, current_path: Path):
        """Limpia audio que no sea la canción actual"""
        current_key = f"audio_{current_path}"
        keys_to_remove = [k for k in self.cache._cache.keys()
                          if k.startswith("audio_") and k != current_key]

        # Mantener solo las 3 canciones más recientes
        if len(keys_to_remove) > 3:
            for key in keys_to_remove[:-3]:
                self.cache.remove(key)


class LazyImageManager:
    """Gestor de imágenes con carga perezosa y redimensionamiento inteligente"""

    def __init__(self):
        self.cache = ResourceCache(max_size=100)

    @lru_cache(maxsize=32)
    def load_icon_cached(self, path: str, size: tuple = None) -> QIcon:
        """Carga iconos con cache LRU incorporado"""
        cache_key = f"icon_{path}_{size}"

        def loader():
            try:
                pixmap = QPixmap(path)

                if size and not pixmap.isNull():
                    pixmap.scaled(
                        size[0], size[1],
                        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                        transformMode=Qt.TransformationMode.SmoothTransformation
                    )
                return QIcon(pixmap)
            except Exception as e:
                print(f"Error loading icon {path}: {e}")
                return QIcon()

        return self.cache.get(cache_key, loader)

    def load_cover_lazy(self, path: Path, size: tuple = (500, 500)) -> QPixmap:
        """Carga portadas de forma perezosa"""
        cache_key = f"cover_{path}_{size}"

        def loader():
            try:
                cover_path = path / "cover.png"
                if cover_path.exists():
                    pixmap = QPixmap(str(cover_path))
                    if not pixmap.isNull():
                        return pixmap.scaled(size[0], size[1],aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,transformMode=Qt.TransformationMode.SmoothTransformation)

                # Fallback a imagen por defecto
                from resources import resource_path
                default_path = resource_path('images/main_window/default.png')
                pixmap = QPixmap(default_path)
                return pixmap.scaled(size[0], size[1],aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,transformMode=Qt.TransformationMode.SmoothTransformation)

            except Exception:
                return QPixmap()

        return self.cache.get(cache_key, loader)

    def extract_cover_lazy(self, mp3_path: Path) -> QPixmap:
        """Extrae portada de MP3 de forma perezosa"""
        cache_key = f"extracted_cover_{mp3_path}"

        def loader():
            try:
                audio = MP3(str(mp3_path))
                if hasattr(audio, 'tags') and audio.tags:
                    for tag in audio.tags.values():
                        if hasattr(tag, 'FrameID') and tag.FrameID == 'APIC':
                            image = Image.open(io.BytesIO(tag.data))
                            image = image.resize((500, 500))

                            # Convertir PIL a QPixmap
                            qimage = image.toqimage() if hasattr(image, 'toqimage') else None
                            if qimage:
                                return QPixmap.fromImage(qimage)

                # Si no hay portada embebida, usar default
                from resources import resource_path
                return QPixmap(resource_path('images/main_window/default.png'))
            except Exception as e:
                print(f"Error extracting cover from {mp3_path}: {e}")
                from resources import resource_path
                return QPixmap(resource_path('images/main_window/default.png'))

        return self.cache.get(cache_key, loader)


class LazyLyricsManager:
    """Gestor de letras con carga perezosa"""

    def __init__(self):
        self.cache = ResourceCache(max_size=50)
        self.processing_lyrics = set()

    def load_lyrics_lazy(self, path: Path) -> list:
        """Carga letras de forma perezosa"""
        cache_key = f"lyrics_{path}"

        def loader():
            lyrics_path = path / "lyrics.lrc"
            if not lyrics_path.exists():
                return []

            try:
                lyrics = []
                current_time = None
                current_text = []

                with open(lyrics_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        import re
                        time_match = re.match(r'\[(\d+):(\d+\.\d+)\]', line)

                        if time_match:
                            if current_time is not None:
                                lyrics.append((current_time, '\n'.join(current_text)))

                            minutes = int(time_match.group(1))
                            seconds = float(time_match.group(2))
                            current_time = minutes * 60 + seconds
                            current_text = [line[time_match.end():]]
                        else:
                            if current_time is not None and line.strip():
                                current_text.append(line.rstrip())

                if current_time is not None:
                    lyrics.append((current_time, '\n'.join(current_text)))

                return lyrics
            except Exception as e:
                print(f"Error loading lyrics from {path}: {e}")
                return []

        return self.cache.get(cache_key, loader)

    def preload_lyrics(self, playlist: list, current_index: int):
        """Precarga letras de canciones adyacentes"""

        def preload_worker():
            for offset in [-1, 1, 2]:  # Anterior, siguiente, y siguiente+1
                idx = (current_index + offset) % len(playlist)
                if 0 <= idx < len(playlist):
                    song_path = playlist[idx]["path"]
                    self.load_lyrics_lazy(song_path)

        thread = threading.Thread(target=preload_worker, daemon=True)
        thread.start()


class LazyPlaylistLoader(QObject):
    """Cargador de playlist con lazy loading"""

    playlist_updated = pyqtSignal(dict)  # Emite cuando se carga una canción
    loading_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cache = ResourceCache(max_size=200)
        self.loading_thread = None

    def load_playlist_lazy(self, path: Path, callback=None):
        """Carga playlist de forma perezosa y asíncrona"""
        if self.loading_thread and self.loading_thread.is_alive():
            print("⚠️ Already loading playlist, skipping...")
            return

        def load_worker():
            print(f"🔍 Starting to scan folder: {path}")
            songs_found = 0

            try:
                json_files = list(path.rglob("*.json"))
                print(f"📄 Found {len(json_files)} JSON files")

                for json_file in json_files:
                    print(f"📖 Processing: {json_file}")

                    try:
                        with open(json_file, "r", encoding='utf-8') as f:
                            data = json.load(f)

                        dir_path = json_file.parent

                        for artist, songs in data.items():
                            for song, _ in songs.items():
                                song_data = {
                                    "artist": artist,
                                    "song": song,
                                    "path": dir_path
                                }

                                print(f"🎵 Found song: {artist} - {song}")
                                self.playlist_updated.emit(song_data)
                                songs_found += 1

                                # Pequeña pausa para no saturar la UI
                                time.sleep(0.01)

                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error in {json_file}: {e}")
                    except Exception as e:
                        print(f"❌ Error loading {json_file}: {e}")

                print(f"✅ Finished loading. Total songs found: {songs_found}")
                self.loading_finished.emit()

            except Exception as e:
                print(f"❌ Fatal error in playlist loading: {e}")
                self.loading_finished.emit()  # Emit anyway to clear loading state

        print("🚀 Starting playlist loading thread...")
        self.loading_thread = threading.Thread(target=load_worker, daemon=True)
        self.loading_thread.start()

    def is_loading(self):
        """Verifica si está cargando actualmente"""
        return self.loading_thread and self.loading_thread.is_alive()


# Clase principal modificada para usar lazy loading
class LazyAudioPlayer:
    """Versión optimizada del AudioPlayer con lazy loading"""

    def __init__(self):
        # Gestores de recursos con lazy loading
        self.audio_manager = LazyAudioManager()
        self.image_manager = LazyImageManager()
        self.lyrics_manager = LazyLyricsManager()
        self.playlist_loader = LazyPlaylistLoader()

        # Variables existentes
        self.playlist = []
        self.current_index = -1
        self.current_channels = []

        # Timer para limpieza automática de cache
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._periodic_cleanup)
        self.cleanup_timer.start(300000)  # Limpieza cada 5 minutos

    def setup_lazy_connections(self):
        """Configura las conexiones para lazy loading"""
        self.playlist_loader.playlist_updated.connect(self._on_song_loaded)
        self.playlist_loader.loading_finished.connect(self._on_playlist_loaded)

    def load_folder_lazy(self, path: Path):
        """Carga carpeta usando lazy loading"""
        self.playlist_loader.load_playlist_lazy(path)

    def _on_song_loaded(self, song_data):
        """Callback cuando se carga una canción"""
        # Verificar si ya existe
        exists = any(
            track['artist'] == song_data['artist'] and
            track['song'] == song_data['song']
            for track in self.playlist
        )

        if not exists:
            self.playlist.append(song_data)
            # Aquí actualizarías la UI (playlist_widget)
            # self._add_song_to_ui(song_data)

    def _on_playlist_loaded(self):
        """Callback cuando termina de cargar la playlist"""
        print(f"Playlist cargada: {len(self.playlist)} canciones")
        # Habilitar controles si es necesario
        # self._enable_playback_controls()

    def play_current_lazy(self):
        """Reproduce la canción actual usando lazy loading"""
        if not (0 <= self.current_index < len(self.playlist)):
            return False

        song = self.playlist[self.current_index]
        song_path = song["path"]

        # Cargar audio de forma perezosa
        sounds = self.audio_manager.load_audio_lazy(song_path)
        if not sounds:
            return False

        # Configurar canales
        self.current_channels = [sound.play() for sound in sounds]

        # Cargar portada de forma perezosa
        cover = self.image_manager.load_cover_lazy(song_path)
        # self.cover_label.setPixmap(cover)  # Actualizar UI

        # Cargar letras de forma perezosa
        lyrics = self.lyrics_manager.load_lyrics_lazy(song_path)
        # self._update_lyrics_display(lyrics)  # Actualizar UI

        # Precargar recursos de las siguientes canciones
        self.audio_manager.preload_next_songs(self.playlist, self.current_index)
        self.lyrics_manager.preload_lyrics(self.playlist, self.current_index)

        return True

    def _periodic_cleanup(self):
        """Limpieza periódica automática de cache"""
        if self.current_index >= 0:
            current_song = self.playlist[self.current_index]
            self.audio_manager.cleanup_old_audio(current_song["path"])

    def cleanup_resources(self):
        """Limpia todos los recursos cargados"""
        self.audio_manager.cache.clear()
        self.image_manager.cache.clear()
        self.lyrics_manager.cache.clear()

    def get_cache_stats(self) -> dict:
        """Obtiene estadísticas de uso de cache"""
        return {
            "audio_cache_size": len(self.audio_manager.cache._cache),
            "image_cache_size": len(self.image_manager.cache._cache),
            "lyrics_cache_size": len(self.lyrics_manager.cache._cache),
            "total_cached_items": (
                    len(self.audio_manager.cache._cache) +
                    len(self.image_manager.cache._cache) +
                    len(self.lyrics_manager.cache._cache)
            )
        }