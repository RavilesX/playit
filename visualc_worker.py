from base_worker import BaseInstallWorker
from platform_utils import IS_WINDOWS, get_visualcpp_install_cmd


class VisualCWorker(BaseInstallWorker):
    def get_commands(self):
        if not IS_WINDOWS:
            return []  # En Linux no se necesita → finished se emite directo
        return [
            {
                'cmd': get_visualcpp_install_cmd(),
                'error_msg': 'Error instalando Visual C++ Redistributable',
                'timeout': 300,
            },
        ]
