import subprocess
from PyQt6.QtCore import QObject, pyqtSignal

class CudaInstallWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            cmd = [
                'pip', 'install',
                'torch==2.6.0',
                'torchvision==0.21.0',
                'torchaudio==2.6.0',
                '--index-url', 'https://download.pytorch.org/whl/cu118',
                '--quiet'
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                self.error.emit(f"Error instalando PyTorch con CUDA:\n{result.stderr}")
                return

            self.finished.emit()
        except subprocess.TimeoutExpired:
            self.error.emit("La instalación excedió el tiempo límite.")
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")