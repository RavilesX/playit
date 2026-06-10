from pathlib import Path
from typing import Dict, Optional, Any, Callable
import threading
import time
import json
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QIcon, QImage
from PIL import Image
import io
from mutagen.mp3 import MP3
import re


class ResourceCache:
    """Cache inteligente con lazy loading y gestión automática de memoria"""

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._cache: Dict[str, Any] = {}
        self._access_times: Dict[str, float] = {}
        self._loading_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.RLock()
        self._cleanup_in_progress = False

        # métricas de rendimiento
        self._hit_count = 0
        self._miss_count = 0
        self._load_times = []

    def get(self, key: str, loader: Callable[[], Any]) -> Any:
        """Obtiene un recurso del cache o lo carga usando lazy loading"""
        start_time = time.time()

        # Verificar cache primero (lectura rápida)
        with self._lock:
            if key in self._cache:
                self._access_times[key] = time.time()
                self._hit_count += 1
                return self._cache[key]
            else:
                self._miss_count += 1

        # Crear lock específico para este recurso si no existe
        if key not in self._loading_locks:
            with self._lock:
                if key not in self._loading_locks:
                    self._loading_locks[key] = threading.Lock()

        # Cargar el recurso (fuera del lock principal)
        with self._loading_locks[key]:
            # Verificar nuevamente por si otro hilo ya lo cargó (double-checked locking)
            with self._lock:
                if key in self._cache:
                    self._access_times[key] = time.time()
                    return self._cache[key]

            # Cargar el recurso
            try:
                resource = loader()
                load_time = time.time() - start_time

                if resource is not None:  # Solo guardar recursos válidos
                    with self._lock:
                        self._cache[key] = resource
                        self._access_times[key] = time.time()

                        # Registrar tiempo de carga
                        self._load_times.append(load_time)
                        if len(self._load_times) > 100:  # Mantener solo los últimos 100
                            self._load_times.pop(0)

                        # Cleanup asíncrono para no bloquear
                        if len(self._cache) > self.max_size:
                            self._schedule_cleanup()

                return resource
            except Exception:
                return None

    def _schedule_cleanup(self):
        """Programa limpieza asíncrona para no bloquear el hilo principal"""
        if self._cleanup_in_progress:
            return

        def cleanup_worker():
            self._cleanup_in_progress = True
            try:
                self._cleanup_if_needed()
            except Exception as e:
                print(f"❌ Error en limpieza: {e}")
            finally:
                self._cleanup_in_progress = False

        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()

    def _cleanup_if_needed(self):
        """Limpia el cache usando estrategia LRU mejorada"""
        with self._lock:
            while len(self._cache) > self.max_size:
                if not self._access_times:
                    break

                # Encontrar el elemento menos recientemente usado
                oldest_key = min(self._access_times.keys(),
                                 key=lambda k: self._access_times[k])

                # Remover el elemento más antiguo
                self._cache.pop(oldest_key, None)
                self._access_times.pop(oldest_key, None)
                self._loading_locks.pop(oldest_key, None)

    def clear(self):
        """Limpia completamente el cache de forma thread-safe"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self._loading_locks.clear()
            self._hit_count = 0
            self._miss_count = 0
            self._load_times.clear()

    def remove(self, key: str):
        """Elimina un elemento específico del cache"""
        with self._lock:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)
            self._loading_locks.pop(key, None)

    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas completas del cache"""
        with self._lock:
            total_requests = self._hit_count + self._miss_count
            hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
            avg_load_time = sum(self._load_times) / len(self._load_times) if self._load_times else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'utilization': len(self._cache) / self.max_size * 100,
                'hit_rate': hit_rate,
                'hits': self._hit_count,
                'misses': self._miss_count,
                'avg_load_time': avg_load_time,
                'keys': list(self._cache.keys()),
                'cleanup_in_progress': self._cleanup_in_progress
            }


class LazyAudioManager:
    """Gestor de audio con carga perezosa"""

    def __init__(self, cache_size: int = 20):
        self.cache = ResourceCache(max_size=cache_size)
        self._loading_semaphore = threading.Semaphore(3)  # Máximo 3 cargas concurrentes

    def load_audio_lazy(self, path: Path) -> Optional[list]:
        cache_key = f"audio_{path}"

        def loader():
            # Usar semáforo para limitar cargas concurrentes
            with self._loading_semaphore:
                try:
                    separated_path = path / "separated"

                    if not separated_path.exists():
                        return None

                    # Verificar que todos los archivos existan antes de cargar
                    track_files = [
                        separated_path / f"{track}.mp3"
                        for track in ("drums", "vocals", "bass", "other")
                    ]

                    if not all(f.exists() for f in track_files):
                        return None

                    return track_files

                except Exception:
                    return None

        return self.cache.get(cache_key, loader)

    def cleanup_old_audio(self, current_path: Path, keep_count: int = 3):
        """Limpia audio manteniendo los elementos más relevantes"""
        try:
            current_key = f"audio_{current_path}"

            with self.cache._lock:
                audio_keys = [k for k in self.cache._cache.keys() if k.startswith("audio_")]

                if len(audio_keys) <= keep_count:
                    return  # No necesita limpieza

                # Mantener la actual + las más recientes
                keys_to_keep = {current_key}
                recent_keys = sorted(
                    [k for k in audio_keys if k != current_key],
                    key=lambda k: self.cache._access_times.get(k, 0),
                    reverse=True
                )[:keep_count - 1]
                keys_to_keep.update(recent_keys)

                # Eliminar el resto
                removed_count = 0
                for key in audio_keys:
                    if key not in keys_to_keep:
                        self.cache.remove(key)
                        removed_count += 1

                # if removed_count > 0:

        except Exception as e:
            print(f"❌ Error limpiando cache de audio: {e}")


class LazyImageManager:
    """Gestor de imágenes con carga perezosa.

    Las portadas se manejan como QImage (no QPixmap) porque se cargan en
    hilos secundarios y Qt solo permite crear QPixmap en el hilo de la GUI.
    """

    def __init__(self, cache_size: int = 100):
        self.cache = ResourceCache(max_size=cache_size)
        self._loading_semaphore = threading.Semaphore(5)  # Max cargas concurrentes para imágenes

    def _scaled(self, image: QImage, size: tuple) -> QImage:
        return image.scaled(
            size[0], size[1],
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
            transformMode=Qt.TransformationMode.SmoothTransformation,
        )

    def get_default_cover(self, size: tuple = (500, 500)) -> QImage:
        """Imagen por defecto para canciones sin portada"""
        cache_key = f"default_cover_{size}"

        def loader():
            from resources import resource_path
            image = QImage(resource_path('images/main_window/default.png'))
            if image.isNull():
                image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
                image.fill(Qt.GlobalColor.darkGray)
            else:
                image = self._scaled(image, size)
            return image

        return self.cache.get(cache_key, loader)

    def load_icon_cached(self, path: str, size: tuple = None) -> QIcon:
        """Carga iconos con cache. Solo debe llamarse desde el hilo de la GUI."""
        cache_key = f"icon_{path}_{size}"

        def loader():
            with self._loading_semaphore:
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    pixmap = QPixmap(size[0] if size else 32, size[1] if size else 32)
                    pixmap.fill(Qt.GlobalColor.lightGray)

                if size and size[0] > 0 and size[1] > 0:
                    pixmap = pixmap.scaled(
                        size[0], size[1],
                        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                        transformMode=Qt.TransformationMode.SmoothTransformation
                    )
                return QIcon(pixmap)

        return self.cache.get(cache_key, loader)

    def load_cover_lazy(self, path: Path, size: tuple = (500, 500)) -> QImage:
        """Carga portadas con múltiples estrategias de fallback"""
        cache_key = f"cover_{path}_{size}"

        def loader():
            with self._loading_semaphore:
                try:
                    # Estrategia 1: Portada específica guardada
                    cover_path = path / "cover.png"
                    if cover_path.exists():
                        image = QImage(str(cover_path))
                        if not image.isNull():
                            return self._scaled(image, size)

                    # Estrategia 2: Buscar archivos de imagen en la carpeta
                    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
                    for img_file in path.iterdir():
                        if img_file.suffix.lower() in image_extensions:
                            image = QImage(str(img_file))
                            if not image.isNull():
                                return self._scaled(image, size)

                    # Estrategia 3: Extraer de un MP3 (el principal, no los stems)
                    mp3_files = list(path.glob("*.mp3"))
                    main_mp3 = next(
                        (f for f in mp3_files if "separated" not in str(f)),
                        mp3_files[0] if mp3_files else None,
                    )
                    if main_mp3:
                        extracted = self.extract_cover_from_mp3(main_mp3)
                        if not extracted.isNull():
                            return self._scaled(extracted, size)

                    # Estrategia 4: Imagen por defecto
                    return self.get_default_cover(size)

                except Exception:
                    return self.get_default_cover(size)

        return self.cache.get(cache_key, loader)

    def extract_cover_from_mp3(self, mp3_path: Path) -> QImage:
        """Extrae la portada embebida (tag APIC) de un MP3"""
        try:
            audio = MP3(str(mp3_path))

            if not (hasattr(audio, 'tags') and audio.tags):
                return self.get_default_cover()

            for tag_value in audio.tags.values():
                if getattr(tag_value, 'FrameID', None) != 'APIC':
                    continue
                if not getattr(tag_value, 'data', None):
                    continue
                try:
                    image = Image.open(io.BytesIO(tag_value.data))
                    if image.mode not in ('RGB', 'RGBA'):
                        image = image.convert('RGB')
                    image.thumbnail((500, 500), Image.Resampling.LANCZOS)

                    buffer = io.BytesIO()
                    image.save(buffer, format='PNG')

                    qimage = QImage()
                    if qimage.loadFromData(buffer.getvalue()):
                        return qimage
                except Exception:
                    continue

        except Exception as e:
            print(f"Error extrayendo portada de {mp3_path}: {e}")

        return self.get_default_cover()


class LazyLyricsManager:
    """Gestor de letras con carga perezosa"""

    def __init__(self, cache_size: int = 50):
        self.cache = ResourceCache(max_size=cache_size)
        self._loading_semaphore = threading.Semaphore(3)

    def load_lyrics_lazy(self, path: Path) -> list:
        """Carga letras de forma perezosa con parsing mejorado"""
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
                    lines = f.readlines()

                for line in lines:
                    line = line.rstrip('\n\r')

                    # Timestamp [mm:ss.xx] inicia un bloque nuevo
                    time_match = re.match(r'\[(\d+):(\d+\.\d+)\]', line)
                    if time_match:
                        if current_time is not None and current_text:
                            lyrics.append((current_time, '\n'.join(current_text)))

                        minutes = int(time_match.group(1))
                        seconds = float(time_match.group(2))
                        current_time = minutes * 60 + seconds
                        current_text = [line[time_match.end():]]
                    elif current_time is not None and line:
                        # Línea sin timestamp: continúa el bloque actual
                        current_text.append(line)

                if current_time is not None and current_text:
                    lyrics.append((current_time, '\n'.join(current_text)))

                return lyrics

            except Exception:
                return []

        return self.cache.get(cache_key, loader)

    def preload_lyrics(self, playlist: list, current_index: int, radius: int = 2):
        """Precarga letras de canciones adyacentes en segundo plano"""

        def preload_worker():
            try:
                for offset in range(-radius, radius + 1):
                    if offset == 0:  # Saltar la actual
                        continue

                    idx = (current_index + offset) % len(playlist)
                    song_path = Path(playlist[idx]["path"])

                    if f"lyrics_{song_path}" not in self.cache._cache:
                        self.load_lyrics_lazy(song_path)

            except Exception as e:
                print(f"Error precargando letras: {e}")

        thread = threading.Thread(target=preload_worker, daemon=True)
        thread.start()


class LazyPlaylistLoader(QObject):
    """Cargador de playlist con lazy loading"""

    playlist_batch_updated = pyqtSignal(list)  # Emite lotes de canciones
    loading_finished = pyqtSignal()
    loading_progress = pyqtSignal(int, int)  # actual, total

    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()
        self.cache = ResourceCache(max_size=200)
        self.loading_thread = None
        self._should_stop = False

    def load_playlist_lazy(self, path: Path, callback=None):
        """Carga playlist de forma optimizada con progreso"""
        if self.loading_thread and self.loading_thread.is_alive():
            self._should_stop = True
            self.loading_thread.join(timeout=2.0)  # Esperar hasta 2 segundos

        self._should_stop = False

        def load_worker():
            songs_found = 0
            files_processed = 0

            try:
                # Primero contar archivos JSON para progreso
                json_files = list(path.rglob("*.json"))
                total_files = len(json_files)

                if total_files == 0:
                    self.loading_finished.emit()
                    return

                batch = []

                for json_file in json_files:
                    if self._should_stop:
                        break

                    files_processed += 1

                    # Emitir progreso
                    self.loading_progress.emit(files_processed, total_files)

                    try:
                        with open(json_file, "r", encoding='utf-8') as f:
                            data = json.load(f)

                        # Validar estructura del JSON
                        if not isinstance(data, dict):
                            continue

                        dir_path = json_file.parent

                        for artist, songs in data.items():
                            if self._should_stop:
                                break

                            if not isinstance(songs, dict):
                                continue

                            for song, song_data in songs.items():
                                if self._should_stop:
                                    break

                                # Validar que existe la carpeta y archivos separados (other.mp3)
                                song_folder = dir_path
                                separated_folder = song_folder / "separated" / "other.mp3"

                                song_info = {
                                    "artist": artist,
                                    "song": song,
                                    "path": song_folder,
                                    "has_separated": separated_folder.exists(),
                                    "json_data": song_data
                                }

                                batch.append(song_info)
                                songs_found += 1

                                if len(batch) >= self.BATCH_SIZE:
                                    self.playlist_batch_updated.emit(batch)
                                    batch = []

                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        continue

                if batch:
                    self.playlist_batch_updated.emit(batch)


            except Exception as e:
                print(f"❌ Error fatal en carga de playlist: {e}")
            finally:
                self.loading_finished.emit()

        self.loading_thread = threading.Thread(target=load_worker, daemon=True)
        self.loading_thread.start()

    def stop_loading(self):
        """Detiene la carga en curso"""
        if self.is_loading():
            self._should_stop = True

    def is_loading(self) -> bool:
        """Verifica si está cargando actualmente"""
        return self.loading_thread and self.loading_thread.is_alive()

    def get_loading_stats(self) -> dict:
        """Obtiene estadísticas de la carga"""
        return {
            'is_loading': self.is_loading(),
            'cache_size': len(self.cache._cache) if self.cache else 0,
            'should_stop': self._should_stop
        }

