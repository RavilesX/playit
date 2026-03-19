from base_worker import BaseInstallWorker
from platform_utils import get_python_install_cmd, get_pip_cmd


class PythonInstallWorker(BaseInstallWorker):
    def get_commands(self):
        return [
            {
                'cmd': get_python_install_cmd(),
                'error_msg': 'Error instalando Python',
                'timeout': 300,
            },
            {
                'cmd': [*get_pip_cmd(), 'install', '--upgrade', 'pip'],
                'error_msg': 'No se pudo actualizar pip',
                'timeout': 120,
                'optional': True,  # No es crítico si falla
            },
        ]
