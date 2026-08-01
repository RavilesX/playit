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

import base64
import json
import logging
import os
import re
import shutil
import io
from pathlib import Path
import mutagen
from mutagen.flac import Picture
from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from platform_utils import (
    run_silent, get_python_cmd, get_data_dir,
    check_pytorch_mps, check_pytorch_cuda,
)

logger = logging.getLogger(__name__)

# Formatos de ENTRADA aceptados: demucs decodifica con torchaudio/ffmpeg, así
# que lee cualquier contenedor que ffmpeg soporte. La salida siempre es mp3
# (flag `--mp3` en `_exec_demucs`), sin importar el formato de origen.
AUDIO_INPUT_EXTS = (
    "mp3", "wav", "flac", "ogg", "oga", "opus", "m4a", "mp4",
    "aac", "aiff", "aif", "wma", "wv", "alac",
)
AUDIO_INPUT_FILTER = (
    "Audio (" + " ".join(f"*.{e}" for e in AUDIO_INPUT_EXTS) + ")"
    ";;Todos los archivos (*)"
)


def _cover_bytes(src) -> bytes | None:
    """Bytes de la portada embebida, sea cual sea el contenedor.

    Cada familia de formatos la guarda distinto: FLAC en `pictures`, Ogg en el
    tag `metadata_block_picture` (Picture en base64), ID3 (mp3/wav/aiff) en
    frames APIC y MP4/M4A en el átomo 'covr'. WMA no se soporta (su WM/Picture
    trae un blob binario propio); simplemente se queda sin portada.
    """
    audio = mutagen.File(src)
    if audio is None:
        return None

    pics = getattr(audio, "pictures", None)  # FLAC
    if pics:
        return bytes(pics[0].data)

    tags = audio.tags
    if not tags:
        return None

    if hasattr(tags, "getall"):  # ID3
        apic = tags.getall("APIC")
        if apic:
            return bytes(apic[0].data)

    covr = tags.get("covr")  # MP4/M4A
    if covr:
        return bytes(covr[0])

    block = tags.get("metadata_block_picture")  # Ogg Vorbis/Opus
    if block:
        return bytes(Picture(base64.b64decode(block[0])).data)

    return None


# Etiquetas por familia de contenedor para cada campo de metadata que se
# guarda en data.json. mutagen expone nombres distintos según el formato:
# ID3 (mp3/wav/aiff) usa frames de 4 letras, MP4/M4A átomos con '©' y
# Vorbis/FLAC/Opus claves en texto plano.
_META_TAGS = {
    "artista": ("TPE1", "\xa9ART", "artist", "author"),
    "cancion": ("TIT2", "\xa9nam", "title"),
    "album": ("TALB", "\xa9alb", "album"),
    "anio": ("TDRC", "TYER", "\xa9day", "date", "year", "originaldate"),
    "genero": ("TCON", "\xa9gen", "genre"),
}


def _tag_value(tags, key: str) -> str:
    """Primer valor de `key` como texto, o '' si no existe."""
    try:
        value = tags.get(key)
    except Exception:
        return ""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value).strip()


def read_source_metadata(src) -> dict:
    """Metadata del origen: artista, canción, álbum, año, género, formato, kbps.

    Solo se incluyen las claves que el archivo realmente trae; la UI muestra
    "Desconocido" para las que falten. Nunca lanza: un archivo sin tags (o que
    mutagen no sepa leer) devuelve solo el formato.
    """
    # De la extensión y no del tipo de mutagen: los stems ya son mp3, así que
    # esta es la única forma de saber después con qué llegó el archivo.
    ext = Path(src).suffix.lstrip(".").upper()
    meta = {"formato": ext} if ext else {}

    try:
        audio = mutagen.File(src)
    except Exception as e:
        logger.error("No se pudo leer metadata de %s: %s", src, e)
        return meta
    if audio is None:
        return meta

    tags = audio.tags
    if tags:
        for field, keys in _META_TAGS.items():
            for key in keys:
                value = _tag_value(tags, key)
                if value:
                    # El año puede venir como fecha completa ("1991-09-24")
                    meta[field] = value[:4] if field == "anio" else value
                    break

    bitrate = getattr(getattr(audio, "info", None), "bitrate", 0)
    if bitrate:
        meta["kbps"] = round(bitrate / 1000)

    return meta


def _sanitize_path_component(name: str) -> str:
    """Vuelve `name` seguro como componente de ruta en cualquier SO.

    artist/song vienen de un QLineEdit sin restricciones: sin esto, "AC/DC"
    crea una subcarpeta anidada (y falla en Windows), ':', '*', '?', '"'
    rompen mkdir en Windows, y ".." escaparía de music_library/.
    """
    sanitized = re.sub(r'[\\/:*?"<>|]', '_', name).strip('. ')
    return sanitized or '_'


class DemucsWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, artist, song, src_path):
        super().__init__()
        self.artist = artist
        self.song = song
        self.src_path = Path(src_path)
        self.base_path = (
            get_data_dir() / "music_library"
            / _sanitize_path_component(artist) / _sanitize_path_component(song)
        )
        self.device_used = "CPU"  # dispositivo con el que realmente corrió demucs

    def run(self):
        try:
            self.progress.emit(5)
            self.base_path.mkdir(parents=True, exist_ok=True)

            self.progress.emit(15)
            self._extract_cover()

            self.progress.emit(17)
            self._create_json()

            self.progress.emit(26)
            self._run_demucs()

            self.progress.emit(83)
            self._organize_output()

            self.progress.emit(100)
            self.finished.emit()
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")

    def _run_demucs(self):
        use_mps = check_pytorch_mps()
        if use_mps:
            self.device_used = "MPS"
        else:
            # Sin -d explícito, demucs usa CUDA si torch la ve; misma detección
            self.device_used = "CUDA" if check_pytorch_cuda() else "CPU"
        result = self._exec_demucs(mps=use_mps)

        # MPS puede fallar según la combinación torch/demucs;
        # reintentar en CPU antes de rendirse
        if result.returncode != 0 and use_mps:
            self._log_failure(result, "Intento con MPS falló, reintentando en CPU")
            self.device_used = "CPU"
            result = self._exec_demucs(mps=False)

        if result.returncode != 0:
            self._log_failure(result, "Intento final falló")
            error_msg = f"Demucs falló con código {result.returncode}"
            detail = self._relevant_output(result)
            if detail:
                error_msg += f"\n{detail}"
            error_msg += f"\n\nLog completo en: {get_data_dir() / 'demucs_error.log'}"
            raise RuntimeError(error_msg)

    def _exec_demucs(self, mps: bool):
        python = get_python_cmd()
        env = None
        if mps:
            # Las ops que MPS no soporta caen a CPU en vez de abortar
            env = os.environ.copy()
            env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        cmd = [
            python, "-m", "demucs",
            "-n", "htdemucs_ft",
            *(["-d", "mps"] if mps else []),
            "-o", str(self.base_path / "separated"),
            "--mp3",
            str(self.src_path),
        ]
        return run_silent(cmd, timeout=7200, env=env)  # 2 horas máximo

    @staticmethod
    def _relevant_output(result) -> str:
        """Últimas líneas útiles del output, sin barras de progreso ni descargas."""
        lines = []
        for stream in (result.stderr or "", result.stdout or ""):
            for ln in stream.splitlines():
                s = ln.strip()
                if not s or "%|" in s or s.startswith("Downloading:"):
                    continue
                lines.append(s)
        return "\n".join(lines[-15:])

    @staticmethod
    def _log_failure(result, context: str):
        try:
            log = get_data_dir() / "demucs_error.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(
                    f"\n===== {context} (código {result.returncode}) =====\n"
                    f"--- stderr ---\n{result.stderr or ''}\n"
                    f"--- stdout ---\n{result.stdout or ''}\n"
                )
        except Exception:
            pass  # el log nunca debe tumbar la separación

    def _extract_cover(self):
        # Track repetido: conservar la portada existente, solo reemplazar stems.
        if (self.base_path / "cover.png").exists():
            return
        try:
            data = _cover_bytes(self.src_path)
            if not data:
                return
            im = Image.open(io.BytesIO(data))
            im.resize((500, 500)).save(self.base_path / "cover.png")
        except Exception as e:
            logger.error("No se pudo extraer portada: %s", e)

    def _create_json(self):
        # Track repetido: el JSON se reescribe con la metadata del archivo
        # nuevo (el anterior ya no existe, se destruye tras separarlo).
        data = {
            self.artist: {
                self.song: {
                    "path": str(self.base_path),
                    "metadata": read_source_metadata(self.src_path),
                }
            }
        }
        (self.base_path / "data.json").write_text(
            json.dumps(data, indent=4), encoding='utf-8'
        )

    def _organize_output(self):
        input_stem = self.src_path.stem
        demucs_dir = self.base_path / "separated" / "htdemucs_ft" / input_stem

        if not demucs_dir.exists():
            # Fallback: intentar con solo el nombre de la canción
            demucs_dir = self.base_path / "separated" / "htdemucs_ft" / self.song
            if not demucs_dir.exists():
                raise FileNotFoundError(
                    f"No se encontró la carpeta de Demucs en: {demucs_dir}"
                )

        target_dir = self.base_path / "separated"
        target_dir.mkdir(exist_ok=True)

        for stem in ("drums", "bass", "other", "vocals"):
            src = demucs_dir / f"{stem}.mp3"
            if not src.exists():
                raise FileNotFoundError(f"Archivo no encontrado: {src}")
            shutil.move(str(src), str(target_dir / f"{stem}.mp3"))

        # Limpiar carpeta temporal de Demucs
        shutil.rmtree(demucs_dir.parent)
