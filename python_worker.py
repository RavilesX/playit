import subprocess
from PyQt6.QtCore import QObject, pyqtSignal

class PythonInstallWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # Instalar Python
            cmd = [
                'winget', 'install', '--id', 'Python.Python.3.13',
                '--override', '/quiet InstallAllUsers=1 PrependPath=1',
                '--accept-source-agreements', '--accept-package-agreements'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                    startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0:
                self.error.emit(f"Error instalando Python:\n{result.stderr}")
                return

            # Actualizar pip
            try:
                subprocess.run(['python', '-m', 'pip', 'install', '--upgrade', 'pip'],
                               capture_output=True, text=True, timeout=120,
                               startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                print(f"Advertencia: No se pudo actualizar pip: {e}")

            self.finished.emit()
        except subprocess.TimeoutExpired:
            self.error.emit("La instalación excedió el tiempo límite.")
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")