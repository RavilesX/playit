import subprocess
import sys
from PyQt6.QtCore import QObject, pyqtSignal

class DemucsInstallWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            # Configuración para ocultar ventanas
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # 1. Instalar demucs vía pip (sin caché para evitar problemas)
            #pip_cmd = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', 'demucs']
            pip_cmd = ['pip', 'install', 'demucs']
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=600,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                self.error.emit(f"Error instalando Demucs:\n{result.stderr}")
                return

            # 2. Verificar que el comando 'demucs' esté disponible
            try:
                subprocess.run(
                    ['demucs', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                self.error.emit("No se pudo ejecutar 'demucs' después de la instalación.")
                return

            # 3. Forzar la descarga del modelo htdemucs_ft
            #    Ejecutar demucs con --help y el modelo especificado; esto carga el modelo si no existe.
            model_cmd = ['demucs', '--help', '-n', 'htdemucs_ft']
            result = subprocess.run(
                model_cmd,
                capture_output=True,
                text=True,
                timeout=600,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                # Si falla, puede ser que el modelo no se descargó; intentamos con un comando alternativo
                model_cmd_alt = ['python', '-c', 'from demucs import pretrained; pretrained.get_model("htdemucs_ft")']
                result = subprocess.run(
                    model_cmd_alt,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode != 0:
                    self.error.emit(f"Error descargando el modelo:\n{result.stderr}")
                    return

            self.finished.emit()
        except subprocess.TimeoutExpired:
            self.error.emit("La instalación excedió el tiempo límite.")
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")