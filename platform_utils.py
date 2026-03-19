import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# ── Detección de plataforma ──────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
IS_WINDOWS = os.name == 'nt'
IS_LINUX = sys.platform.startswith('linux')
IS_MAC = sys.platform == 'darwin'


# ──────────────────────────────────────────────────────────────────────────────
# ── Subprocess helpers ────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def get_hidden_subprocess_kwargs() -> dict:
    if IS_WINDOWS:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            'startupinfo': si,
            'creationflags': subprocess.CREATE_NO_WINDOW,
        }
    return {}


def run_silent(cmd, *, timeout=300, check=False, **extra_kwargs) -> subprocess.CompletedProcess:
    kwargs = {
        'capture_output': True,
        'text': True,
        'timeout': timeout,
        **get_hidden_subprocess_kwargs(),
        **extra_kwargs,
    }
    return subprocess.run(cmd, check=check, **kwargs)


def check_command_exists(cmd: str) -> bool:
    locator = 'where' if IS_WINDOWS else 'which'
    try:
        result = run_silent([locator, cmd], timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def get_python_cmd() -> str:
    if IS_WINDOWS:
        return 'python'
    return 'python3' if check_command_exists('python3') else 'python'


def get_pip_cmd() -> list:
    python = get_python_cmd()
    return [python, '-m', 'pip']


# ──────────────────────────────────────────────────────────────────────────────
# ── Detección de hardware ────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def detect_nvidia_gpu() -> bool:
    if IS_WINDOWS:
        try:
            result = run_silent(
                ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                timeout=10,
            )
            return 'nvidia' in result.stdout.lower()
        except Exception:
            return False
    else:
        if check_command_exists('nvidia-smi'):
            try:
                result = run_silent(['nvidia-smi'], timeout=10)
                return result.returncode == 0
            except Exception:
                pass
        try:
            result = run_silent(['lspci'], timeout=10)
            return 'nvidia' in result.stdout.lower()
        except Exception:
            return False


def check_visual_cpp() -> bool:
    if not IS_WINDOWS:
        return True  # Linux no necesita Visual C++ Redistributable

    try:
        cmd = (
            'reg query '
            '"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall" '
            '/s /f "Visual C++ 2022 X64" 2>nul | findstr /i "DisplayName"'
        )
        result = run_silent(cmd, shell=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def check_pytorch_cuda() -> bool:
    python = get_python_cmd()
    try:
        result = run_silent(
            [python, '-c', 'import torch; exit(0 if torch.cuda.is_available() else 1)'],
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# ── Instaladores por plataforma ──────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def get_ffmpeg_install_cmd() -> list:
    if IS_WINDOWS:
        return [
            'winget', 'install', 'Gyan.FFmpeg',
            '--silent', '--accept-package-agreements', '--accept-source-agreements',
        ]
    elif IS_LINUX:
        return ['sudo', 'apt-get', 'install', '-y', 'ffmpeg']
    elif IS_MAC:
        return ['brew', 'install', 'ffmpeg']
    return []


def get_python_install_cmd() -> list:
    """Retorna el comando para instalar Python según el OS."""
    if IS_WINDOWS:
        return [
            'winget', 'install', '--id', 'Python.Python.3.13',
            '--override', '/quiet InstallAllUsers=1 PrependPath=1',
            '--accept-source-agreements', '--accept-package-agreements',
        ]
    elif IS_LINUX:
        return [
            'sudo', 'apt-get', 'install', '-y',
            'python3', 'python3-pip', 'python3-venv',
        ]
    return []


def get_ytdlp_install_cmd() -> list:
    if IS_WINDOWS:
        return ['winget', 'install', 'yt-dlp', '--accept-source-agreements', '--accept-package-agreements']
    else:
        return [*get_pip_cmd(), 'install', 'yt-dlp']


def get_visualcpp_install_cmd() -> list:
    if IS_WINDOWS:
        return [
            'winget', 'install', 'Microsoft.VCRedist.2015+.x64',
            '--accept-source-agreements', '--accept-package-agreements',
        ]
    return []  # No aplica en Linux/Mac


def get_demucs_install_cmd() -> list:
    return [*get_pip_cmd(), 'install', 'demucs']


def get_cuda_pytorch_install_cmd() -> list:
    return [
        *get_pip_cmd(), 'install',
        'torch==2.6.0', 'torchvision==0.21.0', 'torchaudio==2.6.0',
        '--index-url', 'https://download.pytorch.org/whl/cu118',
        '--quiet',
    ]
