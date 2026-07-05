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

import os
import sys
import subprocess
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# ── Detección de plataforma ──────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
IS_WINDOWS = os.name == 'nt'
IS_LINUX = sys.platform.startswith('linux')
IS_MAC = sys.platform == 'darwin'


# ──────────────────────────────────────────────────────────────────────────────
# ── Rutas de datos ────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def get_data_dir() -> Path:
    """Carpeta base escribible para datos de la app (music_library, logs).

    En Windows/Linux se conserva el comportamiento histórico: rutas relativas
    al directorio de trabajo (el ejecutable se lanza desde su carpeta). En
    macOS eso no sirve: Finder lanza el .app con cwd=/ y Gatekeeper puede
    ejecutarlo translocado en un volumen de solo lectura, así que se usa
    ~/Music/PlayIt.
    """
    if IS_MAC:
        data_dir = Path.home() / 'Music' / 'PlayIt'
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    return Path('.')


# ──────────────────────────────────────────────────────────────────────────────
# ── Subprocess helpers ────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def get_hidden_subprocess_kwargs() -> dict:
    # sys.platform (no IS_WINDOWS): permite al type checker reconocer
    # los atributos de subprocess que solo existen en Windows
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            'startupinfo': si,
            'creationflags': subprocess.CREATE_NO_WINDOW,
        }
    return {}


# Finder lanza las apps con un PATH mínimo (/usr/bin:/bin:...) que no incluye
# las rutas de Homebrew, así que ffmpeg/brew instalados ahí serían invisibles
# para la app y sus subprocesos.
_MAC_EXTRA_PATHS = ('/opt/homebrew/bin', '/usr/local/bin')


def _augment_mac_path(env: dict | None) -> dict | None:
    if not IS_MAC:
        return env
    env = dict(env) if env is not None else os.environ.copy()
    parts = env.get('PATH', '').split(os.pathsep) if env.get('PATH') else []
    for p in _MAC_EXTRA_PATHS:
        if p not in parts:
            parts.append(p)
    env['PATH'] = os.pathsep.join(parts)
    return env


def run_silent(cmd, *, timeout=300, check=False, **extra_kwargs) -> subprocess.CompletedProcess:
    kwargs = {
        'capture_output': True,
        'text': True,
        'timeout': timeout,
        **get_hidden_subprocess_kwargs(),
        **extra_kwargs,
    }
    kwargs['env'] = _augment_mac_path(kwargs.get('env'))
    return subprocess.run(cmd, check=check, **kwargs)


def check_command_exists(cmd: str) -> bool:
    locator = 'where' if IS_WINDOWS else 'which'
    try:
        result = run_silent([locator, cmd], timeout=5)
        return result.returncode == 0
    except Exception:
        return False


# En macOS, Demucs/PyTorch corren en un venv dedicado arm64 nativo dentro de
# get_data_dir(), aislado de cualquier otro python3 en el PATH (p. ej. una
# instalación de Anaconda x86_64/Rosetta, que no soporta MPS). Se crea con
# DemucsInstallWorker; ver MACOS_MPS_UPGRADE.md.
def get_mac_venv_dir() -> Path:
    return get_data_dir() / "mps_env"


def get_mac_venv_python() -> Path:
    return get_mac_venv_dir() / "bin" / "python3"


def get_python_cmd() -> str:
    if IS_WINDOWS:
        return 'python'
    if IS_MAC and get_mac_venv_python().exists():
        return str(get_mac_venv_python())
    return 'python3' if check_command_exists('python3') else 'python'


def get_pip_cmd() -> list:
    python = get_python_cmd()
    return [python, '-m', 'pip']


# ──────────────────────────────────────────────────────────────────────────────
# ── Detección de hardware ────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
def detect_nvidia_gpu() -> bool:
    if IS_MAC:
        return False  # Los Mac modernos no llevan GPU NVIDIA (sin soporte CUDA)
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


def check_pytorch_mps() -> bool:
    """Detecta aceleración MPS (Apple Silicon). El torch normal de pip ya la trae."""
    if not IS_MAC:
        return False
    python = get_python_cmd()
    try:
        result = run_silent(
            [python, '-c',
             'import torch; exit(0 if torch.backends.mps.is_available() else 1)'],
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
    elif IS_MAC:
        return ['brew', 'install', 'python@3.13']
    return []


# Candidatos, en orden de preferencia, para el Python arm64 nativo que
# arranca get_mac_venv_dir(). '/opt/homebrew/bin/python3.13' es el binario
# versionado que instala get_python_install_cmd() en macOS (Homebrew deja los
# alias sin versión fuera del PATH para paquetes python@X.Y); se incluye el
# alias genérico como respaldo por si ya hay otro Python de Homebrew linkeado.
_MAC_BOOTSTRAP_PYTHON_CANDIDATES = (
    '/opt/homebrew/bin/python3.13',
    '/opt/homebrew/bin/python3',
)


def find_mac_arm64_bootstrap_python() -> str | None:
    """Busca un Python arm64 nativo de Homebrew para crear get_mac_venv_dir().

    Se evita depender de get_python_cmd()/PATH porque ahí puede ganar un
    python3 x86_64 bajo Rosetta (p. ej. Anaconda), que no sirve para MPS.
    """
    for candidate in _MAC_BOOTSTRAP_PYTHON_CANDIDATES:
        if not Path(candidate).exists():
            continue
        try:
            result = run_silent(
                [candidate, '-c',
                 'import platform; exit(0 if platform.machine() == "arm64" else 1)'],
                timeout=10,
            )
            if result.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def get_mac_venv_create_cmd() -> list:
    """Comando para crear el venv dedicado a Demucs/MPS. Lista vacía si no
    hay ningún Python arm64 de Homebrew disponible todavía (falta instalarlo)."""
    bootstrap = find_mac_arm64_bootstrap_python()
    if not bootstrap:
        return []
    return [bootstrap, '-m', 'venv', str(get_mac_venv_dir())]


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
