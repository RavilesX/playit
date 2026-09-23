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

"""Dependencias externas (Python, FFmpeg, Demucs, CUDA, yt-dlp, Visual C++):
chequeo en segundo plano e instalación con los workers de `base_worker`.

AudioPlayer solo lee los flags `*_available` y refresca sus menús cuando
llega `changed`; los diálogos de confirmación/resultado cuelgan del padre.
"""
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from base_worker import start_worker_thread
from cuda_worker import CudaInstallWorker
from demucs_install_worker import DemucsInstallWorker
from ffmpeg_worker import FFmpegWorker
from platform_utils import (
    IS_WINDOWS, IS_MAC,
    run_silent, check_command_exists, get_python_cmd, get_data_dir,
    detect_nvidia_gpu, check_visual_cpp, check_pytorch_cuda,
)
from python_worker import PythonInstallWorker
from resources import styled_message_box
from visualc_worker import VisualCWorker
from ytdlp_worker import YTDLPWorker


class DependencyManager(QObject):
    changed = pyqtSignal()    # tras el chequeo inicial o una instalación exitosa
    # Barra de estado: (clave, texto). op_started abre una operación en curso
    # y op_finished la cierra con su resultado
    op_started = pyqtSignal(str, str)
    op_finished = pyqtSignal(str, str)

    def __init__(self, parent):
        super().__init__(parent)
        # vc_available=True fuera de Windows: Linux/macOS no necesitan Visual C++
        self.python_available = False
        self.vc_available = not IS_WINDOWS
        self.ytdlp_available = False
        self.ffmpeg_available = False
        self.gpu_available = False
        self.pytorch_cuda_available = False
        self.demucs_available = True
        self.demucs_install_in_progress = False
        self.cuda_install_in_progress = False
        # nombre → (thread, worker): sin referencia Python el QThread muere corriendo
        self._running: dict[str, tuple] = {}

    # ── Chequeo ──────────────────────────────────────────────────────────
    def check_async(self):
        # Cada chequeo lanza un subproceso (1-2s en total, hasta 15s si demucs
        # tarda); en segundo plano para no retrasar la aparición de la ventana.
        # `changed` cruza al hilo GUI encolada (el receptor vive ahí).
        threading.Thread(target=self._check_all, daemon=True).start()

    def _check_all(self):
        self.check_demucs()
        self.python_available = check_command_exists(get_python_cmd())
        self.ffmpeg_available = check_command_exists('ffmpeg')
        if IS_WINDOWS:
            self.vc_available = check_visual_cpp()
        self.ytdlp_available = check_command_exists('yt-dlp')
        self.gpu_available = detect_nvidia_gpu()
        self.pytorch_cuda_available = check_pytorch_cuda()
        self.changed.emit()

    def check_demucs(self):
        try:
            python = get_python_cmd()
            result = run_silent([python, '-m', 'demucs', '--help'], timeout=15)
            self.demucs_available = result.returncode == 0
        except Exception as e:
            (get_data_dir() / "demucs_error.log").write_text(f"Error checking Demucs: {e}")
            self.demucs_available = False

    # ── Instalación (patrón genérico) ────────────────────────────────────
    def _confirm_install(self, description: str) -> bool:
        reply = styled_message_box(
            self.parent(), "Confirmar instalación",
            f"Se instalará {description}.\n"
            "Esto puede tomar varios minutos y puede requerir permisos de administrador.\n\n"
            "¿Desea continuar?",
            QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    # Guards: cada uno devuelve None (sin bloqueo) o (título, mensaje, icono)
    # para que _run_install muestre el diálogo y aborte la instalación.
    def _guard_brew(self):
        """En macOS los instaladores dependen de Homebrew; avisa si falta."""
        if not IS_MAC or check_command_exists('brew'):
            return None
        return (
            "Homebrew no encontrado",
            "Esta instalación requiere Homebrew y no está instalado.\n"
            "Instálelo desde https://brew.sh y vuelva a intentarlo.",
            QMessageBox.Icon.Warning,
        )

    def _guard_python_required(self, msg: str = "Instale Python primero."):
        if self.python_available:
            return None
        return ("Python requerido", msg, QMessageBox.Icon.Warning)

    def _guard_gpu(self):
        if self.gpu_available:
            return None
        return ("Sin GPU NVIDIA", "No se detectó tarjeta NVIDIA compatible.",
                QMessageBox.Icon.Warning)

    def _guard_in_progress(self, progress_attr: str, label: str):
        if not getattr(self, progress_attr):
            return None
        return ("Instalación en curso",
                f"Ya hay una instalación de {label} en progreso.",
                QMessageBox.Icon.Information)

    def _run_install(self, *, name: str, available_attr: str, already_msg: str,
                     package_desc: str, guards: tuple, worker_factory,
                     success_msg: str, progress_attr: str | None = None, after=None):
        """Flujo común a los 6 instaladores: check de ya-instalado, guards
        específicos (Homebrew/Python/GPU/instalación en curso), confirmación
        y arranque del worker en thread."""
        parent = self.parent()
        if getattr(self, available_attr):
            return styled_message_box(
                parent, f"{name} ya instalado", already_msg, QMessageBox.Icon.Information,
            )
        for guard in guards:
            blocked = guard()
            if blocked:
                return styled_message_box(parent, *blocked)
        if not self._confirm_install(package_desc):
            return
        if progress_attr:
            setattr(self, progress_attr, True)
        worker = worker_factory()
        thread = start_worker_thread(
            worker,
            lambda: self._on_install_success(
                name, available_attr, success_msg, progress_attr=progress_attr, after=after,
            ),
            lambda msg: self._on_install_error(name, msg, progress_attr=progress_attr),
        )
        self._running[name] = (thread, worker)
        self.op_started.emit(name, f"Instalando {name}...")

    def _on_install_success(self, name: str, available_attr: str, message: str,
                            progress_attr: str | None = None, after=None):
        setattr(self, available_attr, True)
        if progress_attr:
            setattr(self, progress_attr, False)
        self.op_finished.emit(name, f"{name} instalado correctamente.")
        if after:
            after()
        self.changed.emit()
        styled_message_box(
            self.parent(), "Instalación completada", message, QMessageBox.Icon.Information
        )

    def _on_install_error(self, name: str, msg: str, progress_attr: str | None = None):
        if progress_attr:
            setattr(self, progress_attr, False)
        self.op_finished.emit(name, f"Error instalando {name}.")
        styled_message_box(self.parent(), "Error de instalación", msg, QMessageBox.Icon.Critical)

    def install_python(self):
        pkg = ("Python mediante winget" if IS_WINDOWS
               else "Python mediante Homebrew" if IS_MAC else "Python")
        self._run_install(
            name="Python", available_attr='python_available',
            already_msg="Python ya está instalado.", package_desc=pkg,
            guards=(self._guard_brew,), worker_factory=PythonInstallWorker,
            success_msg="Python se instaló correctamente.\n"
                        "Es posible que necesite reiniciar la aplicación.",
        )

    def install_vc(self):
        self._run_install(
            name="Visual C++", available_attr='vc_available',
            already_msg="Visual C++ Redistributable ya está instalado.",
            package_desc="Microsoft Visual C++ Redistributable (x64) mediante winget",
            guards=(), worker_factory=VisualCWorker,
            success_msg="Visual C++ Redistributable se instaló correctamente.",
        )

    def install_ffmpeg(self):
        pkg = ("FFmpeg mediante winget" if IS_WINDOWS
               else "FFmpeg mediante Homebrew" if IS_MAC else "FFmpeg")
        self._run_install(
            name="FFmpeg", available_attr='ffmpeg_available',
            already_msg="FFmpeg ya está instalado.", package_desc=pkg,
            guards=(self._guard_brew,), worker_factory=FFmpegWorker,
            success_msg="FFmpeg se instaló correctamente.",
        )

    def install_demucs(self):
        self._run_install(
            name="Demucs", available_attr='demucs_available',
            already_msg="Demucs ya está instalado.",
            package_desc="Demucs y el modelo htdemucs_ft (requiere internet)",
            guards=(
                lambda: self._guard_python_required(
                    "Debe instalar Python antes de instalar Demucs."),
                lambda: self._guard_in_progress('demucs_install_in_progress', "Demucs"),
            ),
            worker_factory=DemucsInstallWorker,
            success_msg="Demucs se instaló y el modelo htdemucs_ft está listo.",
            progress_attr='demucs_install_in_progress',
            after=self.check_demucs,
        )

    def install_cuda(self):
        self._run_install(
            name="CUDA", available_attr='pytorch_cuda_available',
            already_msg="PyTorch+CUDA ya está instalado.",
            package_desc="PyTorch 2.6.0 con soporte CUDA 11.8",
            guards=(
                self._guard_python_required,
                self._guard_gpu,
                lambda: self._guard_in_progress('cuda_install_in_progress', "CUDA"),
            ),
            worker_factory=CudaInstallWorker,
            success_msg="PyTorch con CUDA se instaló correctamente.",
            progress_attr='cuda_install_in_progress',
        )

    def install_ytdlp(self):
        self._run_install(
            name="yt-dlp", available_attr='ytdlp_available',
            already_msg="yt-dlp ya está instalado.", package_desc="yt-dlp",
            guards=(), worker_factory=YTDLPWorker,
            success_msg="yt-dlp se instaló correctamente.\n"
                        "Ahora puede usar 'Descargar MP3...'.",
        )
