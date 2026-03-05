import subprocess
from PyQt6.QtCore import QObject, pyqtSignal

class FFmpegWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        """Instala FFmpeg silenciosamente mediante winget."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            cmd = [
                'winget', 'install', 'Gyan.FFmpeg',
                '--silent',
                '--accept-package-agreements',
                '--accept-source-agreements'
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                self.error.emit(f"Error instalando FFmpeg:\n{result.stderr}")
            else:
                self.finished.emit()
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")