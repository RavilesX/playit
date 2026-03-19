import json
import shutil
import io
from pathlib import Path
from mutagen.mp3 import MP3
from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from platform_utils import run_silent, get_python_cmd, get_hidden_subprocess_kwargs


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
        python = get_python_cmd()
        cmd = [
            python, "-m", "demucs",
            "-n", "htdemucs_ft",
            "-o", str(self.base_path / "separated"),
            "--mp3",
            str(self.src_path),
        ]

        result = run_silent(cmd, timeout=7200)  # 2 horas máximo

        if result.returncode != 0:
            error_msg = f"Demucs falló con código {result.returncode}"
            if result.stderr:
                error_msg += f"\nError: {result.stderr.strip()}"
            raise RuntimeError(error_msg)

    def _extract_cover(self):
        try:
            audio = MP3(self.src_path)
            for tag in audio.tags.values():
                if tag.FrameID == 'APIC':
                    im = Image.open(io.BytesIO(tag.data))
                    im_resized = im.resize((500, 500))
                    im_resized.save(self.base_path / "cover.png")
                    break
        except Exception as e:
            print(f"No se pudo extraer portada: {e}")

    def _create_json(self):
        data = {
            self.artist: {
                self.song: {"path": str(self.base_path)}
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
