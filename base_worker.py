from PyQt6.QtCore import QObject, pyqtSignal
from platform_utils import run_silent


class BaseInstallWorker(QObject):
    """
    Worker genérico para instalaciones en segundo plano.

    Subclases solo necesitan implementar `get_commands()` que retorna
    una lista de comandos a ejecutar secuencialmente.
    """
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def get_commands(self) -> list[dict]:
        """
        Retorna lista de pasos a ejecutar. Cada paso es un dict:
        {
            'cmd': ['comando', 'arg1', ...],
            'error_msg': 'Mensaje si falla',
            'timeout': 300,          # opcional, default 300s
            'optional': False,       # opcional, si True no detiene la cadena
            'shell': False,          # opcional
        }
        """
        raise NotImplementedError("Las subclases deben implementar get_commands()")

    def run(self):
        try:
            for step in self.get_commands():
                cmd = step['cmd']
                error_msg = step.get('error_msg', f"Error ejecutando: {' '.join(cmd)}")
                timeout = step.get('timeout', 300)
                optional = step.get('optional', False)
                shell = step.get('shell', False)

                try:
                    result = run_silent(cmd, timeout=timeout, shell=shell)
                    if result.returncode != 0 and not optional:
                        self.error.emit(f"{error_msg}\n{result.stderr}")
                        return
                except Exception as e:
                    if not optional:
                        self.error.emit(f"{error_msg}\n{str(e)}")
                        return

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"Excepción durante la instalación: {str(e)}")
