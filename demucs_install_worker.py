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

from base_worker import BaseInstallWorker
from platform_utils import (
    get_pip_cmd, get_python_cmd, IS_MAC,
    get_mac_venv_dir, get_mac_venv_python, get_mac_venv_create_cmd,
)


class DemucsInstallWorker(BaseInstallWorker):
    def get_commands(self):
        commands = []

        if IS_MAC:
            # Demucs necesita torch con MPS funcional: se instala en un venv
            # dedicado arm64 nativo, aislado de cualquier python3 x86_64/Rosetta
            # que gane en el PATH (p. ej. Anaconda). Ver MACOS_MPS_UPGRADE.md.
            python = str(get_mac_venv_python())
            if not get_mac_venv_dir().exists():
                venv_cmd = get_mac_venv_create_cmd()
                if not venv_cmd:
                    raise RuntimeError(
                        "No se encontró un Python arm64 nativo de Homebrew para crear "
                        "el entorno de Demucs. Instale Python desde el menú primero."
                    )
                commands.append({
                    'cmd': venv_cmd,
                    'error_msg': 'No se pudo crear el entorno Python nativo (arm64) para Demucs',
                    'timeout': 120,
                })
            pip = [python, '-m', 'pip']
            demucs_pkgs = ['torch', 'torchaudio', 'demucs']
        else:
            python = get_python_cmd()
            pip = get_pip_cmd()
            demucs_pkgs = ['demucs']

        commands += [
            {
                'cmd': [*pip, 'install', *demucs_pkgs],
                'error_msg': 'Error instalando Demucs',
                'timeout': 600,
            },
            {
                'cmd': [python, '-m', 'demucs', '--help'],
                'error_msg': 'No se pudo ejecutar demucs después de la instalación',
                'timeout': 30,
                'optional': True,
            },
            {
                'cmd': [python, '-c',
                        'from demucs import pretrained; pretrained.get_model("htdemucs_ft")'],
                'error_msg': 'Error descargando el modelo htdemucs_ft',
                'timeout': 600,
            },
        ]
        return commands
