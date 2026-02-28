import subprocess
from PyQt6.QtCore import QObject, pyqtSignal

class VisualCWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        """Ejecuta la instalación silenciosa de Visual C++ Redistributable mediante winget."""
        try:
            cmd = [
                'winget', 'install', 'Microsoft.VCRedist.2015+.x64',
                '--accept-source-agreements', '--accept-package-agreements'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self.error.emit(f"Error instalando Visual C++:\n{result.stderr}")
            else:
                self.finished.emit()
        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")