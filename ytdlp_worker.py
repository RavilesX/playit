from base_worker import BaseInstallWorker
from platform_utils import get_ytdlp_install_cmd


class YTDLPWorker(BaseInstallWorker):

    def get_commands(self):
        return [
            {
                'cmd': get_ytdlp_install_cmd(),
                'error_msg': 'Error instalando yt-dlp',
                'timeout': 300,
            },
        ]
