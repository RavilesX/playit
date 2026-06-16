# PlayIt - Reproductor de audio de escritorio con separación de pistas
# Copyright (C) 2025-2026  Ricardo Aviles Sanders
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
