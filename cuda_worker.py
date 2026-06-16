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
from platform_utils import get_cuda_pytorch_install_cmd


class CudaInstallWorker(BaseInstallWorker):
    def get_commands(self):
        return [
            {
                'cmd': get_cuda_pytorch_install_cmd(),
                'error_msg': 'Error instalando PyTorch con CUDA',
                'timeout': 600,
            },
        ]
