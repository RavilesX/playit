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

"""Búsqueda de letras sincronizadas (LRCLIB primero, syncedlyrics de
respaldo) y escritura de lyrics.lrc. Sin Qt: todo corre en hilos de fondo.
"""
import queue
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests

# Texto que se escribe en lyrics.lrc cuando la API no encontró letras; si el
# archivo lo contiene, se reintenta la búsqueda en la próxima carga
LYRICS_NOT_FOUND_TEXT = "Letras no encontradas"


def normalize_text(text: str) -> str:
    """Minúsculas y sin acentos. También lo usan la búsqueda de la playlist
    y los alias de tags de la cola."""
    normalized = unicodedata.normalize('NFKD', text.lower())
    return ''.join(c for c in normalized if not unicodedata.combining(c))


def search_lrclib(artist: str, song: str) -> str:
    """Búsqueda primaria en LRCLIB con coincidencia exacta normalizada."""
    url = f"https://lrclib.net/api/search?q={quote(f'{artist} {song}')}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        norm_artist = normalize_text(artist)
        norm_song = normalize_text(song)
        for result in response.json():
            if (normalize_text(result.get("artistName", "")) == norm_artist
                    and normalize_text(result.get("trackName", "")) == norm_song
                    and result.get("syncedLyrics")):
                return result["syncedLyrics"]
    except Exception:
        pass
    return ""


def search_syncedlyrics(artist: str, song: str) -> str:
    """Fallback multi-proveedor (NetEase, Musixmatch, etc.) con matching fuzzy."""
    try:
        import syncedlyrics
        return syncedlyrics.search(f"{song} {artist}", synced_only=True) or ""
    except Exception:
        return ""


def write_lyrics_file(output_dir: Path, lyrics: str | None):
    """Escribe lyrics.lrc centrando cada línea; sin letras, el placeholder
    que dispara el reintento."""
    if not lyrics:
        content = (
            f'[00:00.00]<center style="color: #ff2626;">'
            f'{LYRICS_NOT_FOUND_TEXT}</center>\n'
        )
    else:
        lines = []
        for line in lyrics.split('\n'):
            if line.strip():
                parts = line.split(']', 1)
                if len(parts) == 2:
                    lines.append(f'{parts[0]}]<center>{parts[1].strip()}</center>')
        content = '\n'.join(lines) + '\n'
    (output_dir / "lyrics.lrc").write_text(content, encoding="utf-8")


def fetch_lyrics(artist: str, song: str, output_dir: Path):
    synced = search_lrclib(artist, song) or search_syncedlyrics(artist, song)
    write_lyrics_file(output_dir, synced)


def needs_lyrics(dir_path) -> bool:
    """True si falta lyrics.lrc o quedó marcado como no encontrado."""
    lrc_path = Path(dir_path) / "lyrics.lrc"
    if not lrc_path.exists():
        return True
    try:
        return LYRICS_NOT_FOUND_TEXT in lrc_path.read_text(encoding="utf-8")
    except Exception:
        return True


class LyricsFetchQueue:
    """Un solo hilo de fondo para no saturar red/CPU al cargar playlists
    grandes: busca las letras que falten.

    El hilo vive todo el proceso bloqueado en `get()` (daemon, sin costo en
    reposo). Antes terminaba tras 5 s sin trabajo y renacía en el próximo
    `put`, pero un `put` justo mientras terminaba veía el hilo aún vivo y su
    canción se quedaba sin buscar hasta el siguiente.
    """

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, dir_path, artist: str, song: str):
        self._queue.put((dir_path, artist, song))

    def _run(self):
        while True:
            dir_path, artist, song = self._queue.get()
            try:
                if needs_lyrics(dir_path):
                    fetch_lyrics(artist, song, Path(dir_path))
            except Exception:
                pass
            finally:
                self._queue.task_done()
