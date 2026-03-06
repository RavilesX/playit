import subprocess
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

class YTDLPDownloadWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def _parse_ytdlp_error(self, stderr: str) -> str:
        """Interpreta la salida de error de yt-dlp y devuelve un mensaje amigable."""
        # Patrones de error comunes
        if "Video unavailable" in stderr:
            return "El video proporcionado no existe o no está disponible. Revisa la URL introducida."
        if "Unsupported URL" in stderr or "not a valid URL" in stderr:
            return "La URL no es válida o no es compatible con YouTube."
        if "This video is private" in stderr:
            return "El video es privado y no se puede acceder."
        if "Sign in to confirm your age" in stderr or "age-restricted" in stderr:
            return "El video tiene restricción de edad. Se requiere inicio de sesión."
        if "HTTP Error 404" in stderr:
            return "El video no fue encontrado (HTTP 404)."
        if "This live stream has ended" in stderr:
            return "La transmisión en vivo ha finalizado y no se puede descargar."
        # Fallback: mostrar las últimas líneas con ERROR o WARNING
        lines = stderr.strip().split('\n')
        relevant = [line for line in lines if "ERROR" in line or "WARNING" in line]
        if relevant:
            return "Error al descargar:\n" + "\n".join(relevant[-3:])
        # Si no hay nada relevante, truncar
        return f"Error en yt-dlp:\n{stderr[:300]}..."

    def run(self):
        try:
            download_dir = Path("./mp3Downloads")
            download_dir.mkdir(exist_ok=True)

            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", str(download_dir / "%(title)s.%(ext)s"),
                self.url
            ]

            # Evitar ventanas emergentes
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                self.finished.emit("Descarga completada correctamente.")
            else:
                error_msg = self._parse_ytdlp_error(result.stderr)
                self.error.emit(error_msg)

        except Exception as e:
            self.error.emit(f"Excepción durante la descarga: {str(e)}")