import os
import subprocess
import shutil
import json
from pathlib import Path
from mutagen.mp3 import MP3
from PIL import Image
import io
from PyQt6.QtCore import QObject, pyqtSignal

class DemucsWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, artist, song, src_path):
        super().__init__()
        self.artist = artist
        self.song = song
        self.src_path = Path(src_path)
        self.base_path = Path("music_library") / artist / song
        self.process = None
        self.file_check_timer = None
        self.file_verification_attempts = 0

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