from base_worker import BaseInstallWorker
from platform_utils import get_pip_cmd, get_python_cmd


class DemucsInstallWorker(BaseInstallWorker):
    def get_commands(self):
        python = get_python_cmd()
        return [
            {
                'cmd': [*get_pip_cmd(), 'install', 'demucs'],
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
