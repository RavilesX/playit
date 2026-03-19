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
