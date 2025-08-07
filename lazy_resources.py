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
            except Exception as e:
                print(f"❌ Error cargando recurso {key}: {e}")
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
        self.preload_futures = {}
        self.current_sounds = []
        self._loading_semaphore = threading.Semaphore(3)  # Máximo 3 cargas concurrentes

    def load_audio_lazy(self, path: Path) -> Optional[list]:
        """Carga audio de forma perezosa con validación robusta"""
        cache_key = f"audio_{path}"

        def loader():
            # Usar semáforo para limitar cargas concurrentes
            with self._loading_semaphore:
                try:
                    print(f"🔄 Cargando audio: {path.name}")
                    sounds = []
                    separated_path = path / "separated"

                    if not separated_path.exists():
                        print(f"⚠️ Carpeta separated no existe: {separated_path}")
                        return None

                    # Verificar que todos los archivos existan antes de cargar
                    track_files = {
                        "drums": separated_path / "drums.mp3",
                        "vocals": separated_path / "vocals.mp3",
                        "bass": separated_path / "bass.mp3",
                        "other": separated_path / "other.mp3"
                    }

                    # Validación previa
                    missing_files = []
                    for track_name, track_path in track_files.items():
                        if not track_path.exists():
                            missing_files.append(f"{track_name}.mp3")

                    if missing_files:
                        print(f"❌ Archivos faltantes: {', '.join(missing_files)}")
                        return None

                    # Cargar todos los archivos
                    for track_name, track_path in track_files.items():
                        try:
                            sound = pygame.mixer.Sound(str(track_path))
                            sounds.append(sound)
                            print(f"✅ Cargado: {track_name}")
                        except pygame.error as e:
                            print(f"❌ Error cargando {track_name}: {e}")
                            return None

                    if len(sounds) == 4:
                        print(f"🎵 Audio completamente cargado: {path.name}")
                        return sounds
                    else:
                        print(f"❌ Solo {len(sounds)}/4 pistas cargadas")
                        return None

                except Exception as e:
                    print(f"❌ Error general cargando audio de {path}: {e}")
                    return None

        return self.cache.get(cache_key, loader)

    def preload_next_songs(self, playlist: list, current_index: int, count: int = 2):
        """Precarga las siguientes canciones de forma inteligente"""

        def preload_worker():
            preloaded = 0
            for i in range(1, count + 1):
                try:
                    next_index = (current_index + i) % len(playlist)
                    if next_index >= len(playlist):
                        continue

                    song_path = Path(playlist[next_index]["path"])
                    cache_key = f"audio_{song_path}"

                    # Solo precargar si no está ya en cache
                    if cache_key not in self.cache._cache:
                        song_info = playlist[next_index]
                        print(f"🔄 Precargando: {song_info['artist']} - {song_info['song']}")

                        result = self.load_audio_lazy(song_path)
                        if result:
                            preloaded += 1
                            print(f"✅ Precargado exitoso: {song_info['song']}")
                        else:
                            print(f"❌ Falló precarga: {song_info['song']}")
                    #else:
                        print(f"📋 Ya en cache: {playlist[next_index]['song']}")

                except Exception as e:
                    print(f"❌ Error precargando canción {i}: {e}")

            print(f"🎯 Precarga completada: {preloaded}/{count} canciones cargadas")

        # Cancelar preload anterior si existe y está corriendo
        if hasattr(self, 'preload_thread') and self.preload_thread.is_alive():
            print("⏹️ Cancelando precarga anterior...")
            return

        self.preload_thread = threading.Thread(target=preload_worker, daemon=True)
        self.preload_thread.start()

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

                if removed_count > 0:
                    print(f"🧹 Limpieza de audio: {removed_count} elementos removidos")

        except Exception as e:
            print(f"❌ Error limpiando cache de audio: {e}")


class LazyImageManager:
    """Gestor de imágenes con carga perezosa y redimensionamiento inteligente"""

    def __init__(self, cache_size: int = 100):
        self.cache = ResourceCache(max_size=cache_size)
        self._default_pixmap = None
        self._loading_semaphore = threading.Semaphore(5)  # Max cargas concurrentes para imágenes

    def get_default_pixmap(self, size: tuple = (500, 500)) -> QPixmap:
        """Obtiene pixmap por defecto de forma lazy con tamaño específico"""
        cache_key = f"default_pixmap_{size}"

        if cache_key not in self.cache._cache:
            try:
                from resources import resource_path
                default_path = resource_path('images/main_window/default.png')
                pixmap = QPixmap(default_path)

                if pixmap.isNull():
                    # Crear pixmap simple si no se encuentra la imagen
                    pixmap = QPixmap(size[0], size[1])
                    pixmap.fill(Qt.GlobalColor.darkGray)
                else:
                    # Redimensionar al tamaño solicitado
                    pixmap = pixmap.scaled(
                        size[0], size[1],
                        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                        transformMode=Qt.TransformationMode.SmoothTransformation
                    )

                # Guardar en cache
                with self.cache._lock:
                    self.cache._cache[cache_key] = pixmap
                    self.cache._access_times[cache_key] = time.time()

            except Exception as e:
                print(f"❌ Error cargando imagen por defecto: {e}")
                pixmap = QPixmap(size[0], size[1])
                pixmap.fill(Qt.GlobalColor.darkGray)

        return self.cache._cache.get(cache_key, QPixmap())

    @lru_cache(maxsize=64)  # Cache para iconos
    def load_icon_cached(self, path: str, size: tuple = None) -> QIcon:
        """Carga iconos con cache LRU mejorado y validación"""
        cache_key = f"icon_{path}_{size}"

        def loader():
            with self._loading_semaphore:
                try:
                    pixmap = QPixmap(path)
                    if pixmap.isNull():
                        print(f"⚠️ No se pudo cargar icono: {path}")
                        # Crear icono de placeholder
                        pixmap = QPixmap(size[0] if size else 32, size[1] if size else 32)
                        pixmap.fill(Qt.GlobalColor.lightGray)

                    if size and size[0] > 0 and size[1] > 0:
                        pixmap = pixmap.scaled(
                            size[0], size[1],
                            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                            transformMode=Qt.TransformationMode.SmoothTransformation
                        )
                    return QIcon(pixmap)
                except Exception as e:
                    print(f"❌ Error cargando icono {path}: {e}")
                    # Icono de error
                    error_pixmap = QPixmap(size[0] if size else 32, size[1] if size else 32)
                    error_pixmap.fill(Qt.GlobalColor.red)
                    return QIcon(error_pixmap)

        return self.cache.get(cache_key, loader)

    def load_cover_lazy(self, path: Path, size: tuple = (500, 500)) -> QPixmap:
        """Carga portadas con múltiples estrategias de fallback"""
        cache_key = f"cover_{path}_{size}"

        def loader():
            with self._loading_semaphore:
                try:
                    print(f"🖼️ Cargando portada: {path.name}")

                    # Estrategia 1: Portada específica guardada
                    cover_path = path / "cover.png"
                    if cover_path.exists():
                        pixmap = QPixmap(str(cover_path))
                        if not pixmap.isNull():
                            print(f"✅ Portada cargada desde archivo: {cover_path}")
                            return pixmap.scaled(
                                size[0], size[1],
                                aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                                transformMode=Qt.TransformationMode.SmoothTransformation
                            )

                    # Estrategia 2: Buscar archivos de imagen en la carpeta
                    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
                    for img_file in path.iterdir():
                        if img_file.suffix.lower() in image_extensions:
                            try:
                                pixmap = QPixmap(str(img_file))
                                if not pixmap.isNull():
                                    print(f"✅ Portada encontrada en carpeta: {img_file.name}")
                                    return pixmap.scaled(
                                        size[0], size[1],
                                        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                                        transformMode=Qt.TransformationMode.SmoothTransformation
                                    )
                            except Exception:
                                continue

                    # Estrategia 3: Extraer de archivos MP3
                    mp3_files = list(path.glob("*.mp3"))
                    if mp3_files:
                        # Buscar primero en el archivo principal (no en separated)
                        main_mp3 = None
                        for mp3_file in mp3_files:
                            if "separated" not in str(mp3_file):
                                main_mp3 = mp3_file
                                break

                        if not main_mp3 and mp3_files:
                            main_mp3 = mp3_files[0]

                        if main_mp3:
                            extracted = self.extract_cover_from_mp3(main_mp3)
                            if extracted and not extracted.isNull():
                                print(f"✅ Portada extraída de MP3: {main_mp3.name}")
                                return extracted.scaled(
                                    size[0], size[1],
                                    aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                                    transformMode=Qt.TransformationMode.SmoothTransformation
                                )

                    # Estrategia 4: Fallback a imagen por defecto
                    print(f"⚠️ No se encontró portada, usando por defecto")
                    return self.get_default_pixmap(size)

                except Exception as e:
                    print(f"❌ Error cargando portada de {path}: {e}")
                    return self.get_default_pixmap(size)

        return self.cache.get(cache_key, loader)

    def extract_cover_from_mp3(self, mp3_path: Path) -> QPixmap:
        """Extrae portada de MP3 con múltiples intentos y validaciones"""
        try:
            print(f"🔍 Extrayendo portada de: {mp3_path.name}")
            audio = MP3(str(mp3_path))

            if not (hasattr(audio, 'tags') and audio.tags):
                print("⚠️ No hay tags en el archivo MP3")
                return self.get_default_pixmap()

            # Buscar tags de imagen (APIC)
            for tag_key, tag_value in audio.tags.items():
                if hasattr(tag_value, 'FrameID') and tag_value.FrameID == 'APIC':
                    try:
                        # Verificar que hay datos de imagen
                        if not hasattr(tag_value, 'data') or not tag_value.data:
                            continue

                        # Procesar imagen
                        image = Image.open(io.BytesIO(tag_value.data))

                        # Convertir a RGB si es necesario
                        if image.mode not in ('RGB', 'RGBA'):
                            image = image.convert('RGB')

                        # Redimensionar manteniendo aspect ratio
                        image.thumbnail((500, 500), Image.Resampling.LANCZOS)

                        # Convertir PIL a QPixmap usando buffer
                        buffer = io.BytesIO()
                        image.save(buffer, format='PNG')
                        buffer.seek(0)

                        pixmap = QPixmap()
                        if pixmap.loadFromData(buffer.getvalue()):
                            print("✅ Portada extraída exitosamente")
                            return pixmap
                        else:
                            print("⚠️ Error convirtiendo imagen a QPixmap")

                    except Exception as e:
                        print(f"⚠️ Error procesando tag de imagen: {e}")
                        continue

        except Exception as e:
            print(f"❌ Error extrayendo portada de {mp3_path}: {e}")

        return self.get_default_pixmap()

    def preload_covers(self, playlist: list, current_index: int, radius: int = 2):
        """Precarga portadas de canciones cercanas"""

        def preload_worker():
            preloaded = 0
            for offset in range(-radius, radius + 1):
                if offset == 0:  # Saltar la actual
                    continue

                try:
                    idx = (current_index + offset) % len(playlist)
                    if 0 <= idx < len(playlist):
                        song_path = Path(playlist[idx]["path"])
                        cache_key = f"cover_{song_path}_(500, 500)"

                        # Solo precargar si no está en cache
                        if cache_key not in self.cache._cache:
                            result = self.load_cover_lazy(song_path, (500, 500))
                            if result and not result.isNull():
                                preloaded += 1

                except Exception as e:
                    print(f"❌ Error precargando portada {offset}: {e}")

            print(f"🖼️ Portadas precargadas: {preloaded}")

        thread = threading.Thread(target=preload_worker, daemon=True)
        thread.start()

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
                print(f"⚠️ Archivo de letras no encontrado: {lyrics_path}")
                return []

            try:
                lyrics = []
                current_time = None
                current_text = []

                with open(lyrics_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for line in lines:
                    line = line.rstrip('\n\r')

                    # Buscar timestamp [mm:ss.xx]
                    time_match = re.match(r'\[(\d+):(\d+\.\d+)\]', line)


                    if time_match:
                        # Guardar el bloque anterior
                        if current_time is not None and current_text:
                            lyrics.append((current_time, '\n'.join(current_text)))


                        # Nuevo timestamp
                        minutes = int(time_match.group(1))
                        seconds = float(time_match.group(2))
                        current_time = minutes * 60 + seconds
                        current_text = [line[time_match.end():]]
                    else:
                        # Línea sin timestamp: agregar al texto actual
                        if current_time is not None and line:
                            current_text.append(line)

                # Agregar el último bloque
                if current_time is not None and current_text:
                    lyrics.append((current_time, '\n'.join(current_text)))

                print(f"🎤 Letras cargadas: {len(lyrics)} bloques de texto")
                return lyrics

            except Exception as e:
                print(f"❌ Error cargando letras de {path}: {e}")
                return []

        return self.cache.get(cache_key, loader)

    def preload_lyrics(self, playlist: list, current_index: int, radius: int = 2):
        """Precarga letras de canciones adyacentes de forma eficiente"""

        def preload_worker():
            preloaded = 0
            try:
                for offset in range(-radius, radius + 1):
                    if offset == 0:  # Saltar la actual
                        continue

                    idx = (current_index + offset) % len(playlist)
                    if 0 <= idx < len(playlist):
                        song_path = Path(playlist[idx]["path"])
                        cache_key = f"lyrics_{song_path}"

                        # Solo precargar si no está en cache
                        if cache_key not in self.cache._cache:
                            result = self.load_lyrics_lazy(song_path)
                            if result:
                                preloaded += 1

                print(f"🎤 Letras precargadas: {preloaded}")

            except Exception as e:
                print(f"❌ Error precargando letras: {e}")

        thread = threading.Thread(target=preload_worker, daemon=True)
        thread.start()

    def search_lyrics(self, query: str, lyrics: list) -> list:
        """Busca texto en las letras cargadas"""
        if not query or not lyrics:
            return []

        query_lower = query.lower()
        results = []

        for timestamp, text in lyrics:
            if query_lower in text.lower():
                results.append((timestamp, text))

        return results


class LazyPlaylistLoader(QObject):
    """Cargador de playlist con lazy loading"""

    playlist_updated = pyqtSignal(dict)  # Emite cuando se carga una canción
    loading_finished = pyqtSignal()
    loading_progress = pyqtSignal(int, int)  # actual, total

    def __init__(self):
        super().__init__()
        self.cache = ResourceCache(max_size=200)
        self.loading_thread = None
        self._should_stop = False

    def load_playlist_lazy(self, path: Path, callback=None):
        """Carga playlist de forma optimizada con progreso"""
        if self.loading_thread and self.loading_thread.is_alive():
            print("⚠️ Ya hay una carga en progreso, cancelando anterior...")
            self._should_stop = True
            self.loading_thread.join(timeout=2.0)  # Esperar hasta 2 segundos

        self._should_stop = False

        def load_worker():
            print(f"🔍 Iniciando escaneo de carpeta: {path}")
            songs_found = 0
            files_processed = 0

            try:
                # Primero contar archivos JSON para progreso
                json_files = list(path.rglob("*.json"))
                total_files = len(json_files)
                print(f"📄 Encontrados {total_files} archivos JSON")

                if total_files == 0:
                    print("⚠️ No se encontraron archivos JSON en la carpeta")
                    self.loading_finished.emit()
                    return

                for json_file in json_files:
                    if self._should_stop:
                        print("🛑 Carga cancelada por el usuario")
                        break

                    files_processed += 1
                    print(f"📖 Procesando ({files_processed}/{total_files}): {json_file.name}")

                    # Emitir progreso
                    self.loading_progress.emit(files_processed, total_files)

                    try:
                        with open(json_file, "r", encoding='utf-8') as f:
                            data = json.load(f)

                        # Validar estructura del JSON
                        if not isinstance(data, dict):
                            print(f"⚠️ Formato JSON inválido en {json_file}")
                            continue

                        dir_path = json_file.parent

                        for artist, songs in data.items():
                            if self._should_stop:
                                break

                            if not isinstance(songs, dict):
                                print(f"⚠️ Estructura de canciones inválida para {artist}")
                                continue

                            for song, song_data in songs.items():
                                if self._should_stop:
                                    break

                                # Validar que existe la carpeta separada
                                song_folder = dir_path
                                separated_folder = song_folder / "separated"

                                song_info = {
                                    "artist": artist,
                                    "song": song,
                                    "path": song_folder,
                                    "has_separated": separated_folder.exists(),
                                    "json_data": song_data
                                }

                                print(f"🎵 Canción encontrada: {artist} - {song}")
                                self.playlist_updated.emit(song_info)
                                songs_found += 1

                                # Pequeña pausa para no saturar la UI
                                time.sleep(0.001)

                    except json.JSONDecodeError as e:
                        print(f"❌ Error JSON en {json_file}: {e}")
                        continue
                    except Exception as e:
                        print(f"❌ Error procesando {json_file}: {e}")
                        continue

                print(f"✅ Carga completada. Canciones encontradas: {songs_found}")

            except Exception as e:
                print(f"❌ Error fatal en carga de playlist: {e}")
            finally:
                self.loading_finished.emit()

        print("🚀 Iniciando hilo de carga de playlist...")
        self.loading_thread = threading.Thread(target=load_worker, daemon=True)
        self.loading_thread.start()

    def stop_loading(self):
        """Detiene la carga en curso"""
        if self.is_loading():
            print("⏹️ Deteniendo carga de playlist...")
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


# Clase principal modificada para usar lazy loading
class LazyAudioPlayer:
    """Versión optimizada del AudioPlayer con lazy loading"""

    def __init__(self, config=None):
        # Configuración
        if config is None:
            from lazy_config import LazyLoadingConfig
            config = LazyLoadingConfig.create_adaptive_config()

        self.config = config

        # Gestores de recursos con lazy loading
        self.audio_manager = LazyAudioManager(config.audio_cache_size)
        self.image_manager = LazyImageManager(config.image_cache_size)
        self.lyrics_manager = LazyLyricsManager(config.lyrics_cache_size)
        self.playlist_loader = LazyPlaylistLoader()

        # Variables de estado
        self.playlist = []
        self.current_index = -1
        self.current_channels = []
        self.playback_state = "Stopped"

        # Timer para limpieza automática
        self._setup_cleanup_timer()

        print("🎵 LazyAudioPlayer inicializado con lazy loading completo")

    def _setup_cleanup_timer(self):
        """Configura timer de limpieza automática"""
        try:
            from PyQt6.QtCore import QTimer
            self.cleanup_timer = QTimer()
            self.cleanup_timer.timeout.connect(self._periodic_cleanup)
            self.cleanup_timer.start(self.config.cleanup_interval_ms)
            print(f"⏰ Timer de limpieza configurado: {self.config.cleanup_interval_ms}ms")
        except Exception as e:
            print(f"⚠️ No se pudo configurar timer de limpieza: {e}")

    def setup_lazy_connections(self):
        """Configura las conexiones para lazy loading"""
        self.playlist_loader.playlist_updated.connect(self._on_song_loaded)
        self.playlist_loader.loading_finished.connect(self._on_playlist_loaded)
        self.playlist_loader.loading_progress.connect(self._on_loading_progress)

    def load_folder_lazy(self, path: Path):
        """Carga carpeta usando lazy loading con validación"""
        if not path.exists() or not path.is_dir():
            print(f"❌ Ruta inválida: {path}")
            return False

        print(f"📁 Cargando carpeta: {path}")
        self.playlist_loader.load_playlist_lazy(path)
        return True

    def _on_song_loaded(self, song_data):
        """Callback mejorado cuando se carga una canción"""
        try:
            # Verificar duplicados de forma más eficiente
            song_id = f"{song_data['artist']}|{song_data['song']}"
            existing_ids = {f"{track['artist']}|{track['song']}" for track in self.playlist}

            if song_id not in existing_ids:
                self.playlist.append(song_data)
                print(f"➕ Añadida: {song_data['artist']} - {song_data['song']}")

        except Exception as e:
            print(f"❌ Error procesando canción cargada: {e}")

    def _on_playlist_loaded(self):
        """Callback cuando termina de cargar la playlist"""
        print(f"✅ Playlist completamente cargada: {len(self.playlist)} canciones")

    def _on_loading_progress(self, current, total):
        """Callback de progreso de carga"""
        percentage = int((current / total) * 100) if total > 0 else 0
        print(f"📊 Progreso de carga: {current}/{total} ({percentage}%)")

    def play_current_lazy(self):
        """Reproduce la canción actual usando lazy loading optimizado"""
        if not (0 <= self.current_index < len(self.playlist)):
            print("❌ Índice de canción inválido")
            return False

        song = self.playlist[self.current_index]
        song_path = Path(song["path"])

        print(f"▶️ Reproduciendo: {song['artist']} - {song['song']}")

        # Cargar audio de forma perezosa
        sounds = self.audio_manager.load_audio_lazy(song_path)
        if not sounds:
            print("❌ No se pudo cargar el audio")
            return False

        # Configurar reproducción (esto dependería de tu implementación específica)
        self.current_channels = sounds  # Simplificado para el ejemplo
        self.playback_state = "Playing"

        # Precargar recursos de las siguientes canciones
        self.audio_manager.preload_next_songs(self.playlist, self.current_index)
        self.lyrics_manager.preload_lyrics(self.playlist, self.current_index)
        self.image_manager.preload_covers(self.playlist, self.current_index)

        print("✅ Reproducción iniciada exitosamente")
        return True

    def _periodic_cleanup(self):
        """Limpieza periódica automática optimizada"""
        try:
            if self.current_index >= 0:
                current_song = self.playlist[self.current_index]
                current_path = Path(current_song["path"])

                # Limpiar solo si es necesario
                audio_stats = self.audio_manager.cache.get_stats()
                if audio_stats['utilization'] > 80:  # Solo si el cache está > 80% lleno
                    self.audio_manager.cleanup_old_audio(current_path)

        except Exception as e:
            print(f"❌ Error en limpieza periódica: {e}")

    def cleanup_all_resources(self):
        """Limpia todos los recursos cargados con estadísticas"""
        try:
            before_stats = self.get_cache_stats()

            self.audio_manager.cache.clear()
            self.image_manager.cache.clear()
            self.lyrics_manager.cache.clear()

            after_stats = self.get_cache_stats()

            cleared_items = before_stats['total_cached_items'] - after_stats['total_cached_items']
            print(f"🧹 Limpieza completa: {cleared_items} elementos eliminados")

        except Exception as e:
            print(f"❌ Error en limpieza completa: {e}")

    # def cleanup_resources(self):
    #     """Limpia todos los recursos cargados"""
    #     self.audio_manager.cache.clear()
    #     self.image_manager.cache.clear()
    #     self.lyrics_manager.cache.clear()

    def get_cache_stats(self) -> dict:
        """Obtiene estadísticas completas de uso de cache"""
        try:
            audio_stats = self.audio_manager.cache.get_stats()
            image_stats = self.image_manager.cache.get_stats()
            lyrics_stats = self.lyrics_manager.cache.get_stats()

            return {
                "audio_cache": audio_stats,
                "image_cache": image_stats,
                "lyrics_cache": lyrics_stats,
                "total_cached_items": (
                        audio_stats['size'] + image_stats['size'] + lyrics_stats['size']
                ),
                "overall_hit_rate": (
                        (audio_stats['hits'] + image_stats['hits'] + lyrics_stats['hits']) /
                        max(1, audio_stats['hits'] + image_stats['hits'] + lyrics_stats['hits'] +
                            audio_stats['misses'] + image_stats['misses'] + lyrics_stats['misses']) * 100
                ),
                "memory_utilization": {
                    "audio": audio_stats['utilization'],
                    "images": image_stats['utilization'],
                    "lyrics": lyrics_stats['utilization']
                }
            }
        except Exception as e:
            print(f"❌ Error obteniendo estadísticas: {e}")
            return {"error": str(e)}

    def get_performance_report(self) -> str:
        """Genera reporte completo de rendimiento"""
        try:
            stats = self.get_cache_stats()

            report_lines = [
                "🚀 REPORTE DE RENDIMIENTO LAZY LOADING",
                "=" * 50,
                f"📊 ESTADÍSTICAS GENERALES:",
                f"   ├─ Total elementos en cache: {stats['total_cached_items']}",
                f"   ├─ Hit rate general: {stats['overall_hit_rate']:.1f}%",
                f"   └─ Canciones en playlist: {len(self.playlist)}",
                "",
                f"💾 UTILIZACIÓN DE CACHE:",
                f"   ├─ Audio: {stats['memory_utilization']['audio']:.1f}%",
                f"   ├─ Imágenes: {stats['memory_utilization']['images']:.1f}%",
                f"   └─ Letras: {stats['memory_utilization']['lyrics']:.1f}%",
                "",
                f"⚡ RENDIMIENTO POR TIPO:",
                f"   ├─ Audio - Hits: {stats['audio_cache']['hits']}, Misses: {stats['audio_cache']['misses']}",
                f"   ├─ Imágenes - Hits: {stats['image_cache']['hits']}, Misses: {stats['image_cache']['misses']}",
                f"   └─ Letras - Hits: {stats['lyrics_cache']['hits']}, Misses: {stats['lyrics_cache']['misses']}",
                "",
                f"🎵 ESTADO ACTUAL:",
                f"   ├─ Canción actual: {self.current_index + 1 if self.current_index >= 0 else 'Ninguna'}/{len(self.playlist)}",
                f"   ├─ Estado: {self.playback_state}",
                f"   └─ Carga en progreso: {'Sí' if self.playlist_loader.is_loading() else 'No'}"
            ]

            return "\n".join(report_lines)

        except Exception as e:
            return f"❌ Error generando reporte: {e}"