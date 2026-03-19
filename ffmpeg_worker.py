from base_worker import BaseInstallWorker
from platform_utils import get_ffmpeg_install_cmd


class FFmpegWorker(BaseInstallWorker):
    def get_commands(self):
        return [
            {
                'cmd': get_ffmpeg_install_cmd(),
                'error_msg': 'Error instalando FFmpeg',
                'timeout': 300,
            },
        ]
