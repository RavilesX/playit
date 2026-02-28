import subprocess
from PyQt6.QtCore import QObject, pyqtSignal

class PythonInstallWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        """Ejecuta la instalación silenciosa de Python 3.11 mediante winget."""
        try:
            # Comando winget para instalar Python 3.11 silenciosamente
            cmd = [
                'winget', 'install', '--id', 'Python.Python.3.11',
                '--version', '3.11.0',
                '--override', '/quiet InstallAllUsers=1 PrependPath=1',
                '--accept-source-agreements', '--accept-package-agreements'
            ]
            # Ejecutar sin capturar salida para que se vea la ventana de UAC si es necesario
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0:
                self.error.emit(f"Error instalando Python:\n{result.stderr}")
            else:
                self.finished.emit()
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")