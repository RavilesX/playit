from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from platform_utils import run_silent


class YTDLPDownloadWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    _ERROR_PATTERNS = {
        "Video unavailable": "El video no existe o no está disponible. Revisa la URL.",
        "Unsupported URL": "La URL no es válida o no es compatible con YouTube.",
        "not a valid URL": "La URL no es válida o no es compatible con YouTube.",
        "This video is private": "El video es privado y no se puede acceder.",
        "Sign in to confirm your age": "El video tiene restricción de edad.",
        "age-restricted": "El video tiene restricción de edad.",
        "HTTP Error 404": "El video no fue encontrado (HTTP 404).",
        "This live stream has ended": "La transmisión en vivo ha finalizado.",
    }

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def _parse_ytdlp_error(self, stderr: str) -> str:
        for pattern, message in self._ERROR_PATTERNS.items():
            if pattern in stderr:
                return message

        lines = stderr.strip().split('\n')
        relevant = [l for l in lines if 'ERROR' in l or 'WARNING' in l]
        if relevant:
            return "Error al descargar:\n" + "\n".join(relevant[-3:])
        return f"Error en yt-dlp:\n{stderr[:300]}..."

    def run(self):
        try:
            download_dir = Path("./mp3Downloads")
            download_dir.mkdir(exist_ok=True)

            cmd = [
                "yt-dlp", "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", str(download_dir / "%(title)s.%(ext)s"),
                self.url,
            ]

            result = run_silent(cmd, timeout=600)

            if result.returncode == 0:
                self.finished.emit("Descarga completada correctamente.")
            else:
                self.error.emit(self._parse_ytdlp_error(result.stderr))

        except Exception as e:
            self.error.emit(f"Excepción durante la descarga: {str(e)}")
