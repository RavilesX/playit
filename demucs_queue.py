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

"""Cola de separación con Demucs: un DemucsWorker a la vez en su QThread,
el cronómetro opcional (modal por canción o resumen por lote) y la
verificación de archivos al terminar la cola.

AudioPlayer solo encola (`add` / `add_batch`), pinta `status_text()` cuando
llega `changed` y agrega a la playlist la carpeta que llega en `song_ready`;
los diálogos cuelgan del padre.
"""
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from demucs_worker import DemucsWorker, _sanitize_path_component
from dialogs import BatchTimingDialog, format_elapsed
from resources import bg_image, styled_message_box

VERIFICATION_MAX_ATTEMPTS = 60
VERIFICATION_INTERVAL_MS = 30_000


class DemucsQueue(QObject):
    changed = pyqtSignal()          # progreso, cola o estado activo cambió
    # Carpeta de una canción recién separada. Solo esa: re-escanear toda la
    # librería en el hilo GUI congelaba 0.25-1.4 s por canción (940 temas)
    song_ready = pyqtSignal(Path)

    def __init__(self, parent, library: Path):
        super().__init__(parent)
        self.library = library
        self.queue: list[dict] = []
        self.active = False
        self.progress = 0
        self.processing_multiple = False
        self.thread = None
        self.worker = None
        self.last_in_queue = {"artist": "", "song": ""}
        self._current_job: dict | None = None
        # Cronómetro por lote: {batch_id: [renglones]}. El resumen sale una
        # sola vez, cuando ya no queda ningún trabajo de ese lote.
        self._batch_timings: dict[int, list[dict]] = {}
        self._batch_seq = 0
        self._verification_attempts = 0
        self.verification_timer: QTimer | None = None

    def status_text(self) -> str:
        """Parte de la barra de estado: progreso del trabajo actual y la cola."""
        parts = []
        if self.active:
            filled = int(self.progress / 100 * 10)
            parts.append(f"Separando: {'■' * filled}{'▢' * (10 - filled)} {self.progress}%")
        if self.queue:
            parts.append(f"En cola: {len(self.queue)}")
        return " | ".join(parts)

    # ── Encolar ──────────────────────────────────────────────────────────
    def add(self, artist: str, song: str, file_path: str, timed: bool = False):
        self.last_in_queue = {"artist": artist, "song": song}
        self.queue.append({"artist": artist, "song": song,
                           "file_path": file_path, "timed": timed})
        if not self.active:
            self._process_next_job()
        else:
            self.processing_multiple = True
            self.changed.emit()

    def add_batch(self, jobs: list[dict], timed: bool = False):
        """Encola de golpe los trabajos de un lote del diálogo de división.

        Los nombres ya vienen resueltos (SplitDialog los valida antes de
        emitir), así que aquí solo se llena la cola: arranca el primero y el
        resto espera su turno, igual que al agregar canciones una por una.
        """
        if not jobs:
            return

        # batch_id agrupa los renglones del cronómetro: sin él, dos lotes
        # encolados uno tras otro mezclarían sus resúmenes.
        batch_id = self._batch_seq
        self._batch_seq += 1
        for job in jobs:
            self.queue.append({
                "artist": job["artist"], "song": job["song"],
                "file_path": job["file_path"], "timed": timed,
                "batch_id": batch_id,
            })
        self.last_in_queue = {"artist": jobs[-1]["artist"], "song": jobs[-1]["song"]}

        if self.active:
            self.processing_multiple = True
            self.changed.emit()
            return

        # Con más de un trabajo pendiente, processing_multiple evita un
        # diálogo de error por cada track fallido en medio del lote.
        self.processing_multiple = len(self.queue) > 1
        self._process_next_job()

    # ── Ciclo de un trabajo ──────────────────────────────────────────────
    def _process_next_job(self):
        if not self.queue:
            self.active = False
            self.processing_multiple = False
            # Se suelta el trabajo ya terminado: _finish_timed_job mira este
            # atributo para saber si al lote todavía le queda algo corriendo.
            self._current_job = None
            self.changed.emit()
            return
        self._start_job(self.queue.pop(0))

    def _start_job(self, job: dict):
        try:
            self.cleanup()
            self.active = True
            self.progress = 0
            # Cronómetro opcional del proceso (benchmark de hardware)
            job['t0'] = time.monotonic()
            self._current_job = job
            self.changed.emit()

            self.worker = DemucsWorker(job['artist'], job['song'], job['file_path'])
            self.thread = QThread()
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self._on_success)
            self.worker.error.connect(self._on_error)
            self.worker.progress.connect(self._on_progress)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.start()
        except Exception as e:
            # _on_error ya avanza la cola; avanzar otra vez aquí
            # arrancaba un trabajo y lo pisaba con el siguiente.
            self._on_error(f"Error iniciando separación: {e}")

    def cleanup(self):
        """Detiene el trabajo en curso (también al cerrar la ventana)."""
        try:
            if self.thread and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(1000)
        except Exception:
            pass
        try:
            if self.worker:
                self.worker.deleteLater()
        except Exception:
            pass
        self.thread = None
        self.worker = None

    def _on_success(self):
        job = self._current_job
        device = getattr(self.worker, 'device_used', 'CPU')
        if job:
            self.song_ready.emit(self._song_folder(job['artist'], job['song']))
        self._finish_job()
        self._process_next_job()
        if not self.queue and self.processing_multiple:
            self.processing_multiple = False
            self._start_file_verification()
        # Al final (con el track ya en la playlist y el siguiente trabajo de la
        # cola ya lanzado, para que el diálogo modal no la detenga)
        self._finish_timed_job(job, device)

    def _finish_job(self):
        self.active = False
        self.changed.emit()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(500)
        self.thread = None
        self.worker = None

    def _on_error(self, error_msg: str):
        job = self._current_job
        self._finish_job()
        if not self.processing_multiple:
            styled_message_box(self.parent(), "Error", error_msg, QMessageBox.Icon.Critical)
        self._process_next_job()
        # Un track fallido también cierra su renglón: si no, un lote cuyo
        # último trabajo falla nunca mostraría el resumen.
        self._finish_timed_job(job, "", failed=True)

    def _on_progress(self, value: int):
        self.progress = value
        self.changed.emit()

    # ── Cronómetro ───────────────────────────────────────────────────────
    def _finish_timed_job(self, job: dict | None, device: str, failed: bool = False):
        """Cierra el cronómetro de un trabajo terminado.

        Una canción suelta saca su modal ahí mismo; una del lote solo anota
        su renglón y el resumen sale cuando el lote entero termina.
        """
        if not job or not job.get('timed'):
            return

        elapsed = time.monotonic() - job['t0']
        batch_id = job.get('batch_id')
        if batch_id is None:
            if not failed:
                styled_message_box(
                    self.parent(), "Tiempo de separación",
                    f"{job['artist']} - {job['song']}\n\n"
                    f"El proceso tomó {format_elapsed(elapsed)}.\n"
                    f"Procesado con: {device}",
                    QMessageBox.Icon.Information,
                )
            return

        self._batch_timings.setdefault(batch_id, []).append({
            "artist": job['artist'], "song": job['song'],
            "elapsed": elapsed, "device": device, "failed": failed,
        })

        # El lote terminó cuando ninguno de sus trabajos sigue en la cola ni
        # corriendo. Se mira _current_job porque para cuando llegamos aquí el
        # siguiente ya salió de la cola. Canciones agregadas a mano en medio
        # del lote no lo alargan: no llevan este batch_id.
        running = self._current_job
        pending = self.queue + ([running] if running else [])
        if not any(j.get('batch_id') == batch_id for j in pending):
            self._show_batch_timing_summary(batch_id)

    def _show_batch_timing_summary(self, batch_id: int):
        rows = self._batch_timings.pop(batch_id, [])
        if not rows:
            return
        dialog = BatchTimingDialog(self.parent(), rows)
        bg_image(dialog, 'images/split_dialog/split.png')
        dialog.exec()

    # ── Verificación de archivos al terminar la cola ─────────────────────
    def _start_file_verification(self):
        self._verification_attempts = 0
        self.verification_timer = QTimer(self)
        self.verification_timer.timeout.connect(self._check_files)
        self.verification_timer.start(VERIFICATION_INTERVAL_MS)
        self._check_files()

    def _check_files(self):
        if self._verification_attempts >= VERIFICATION_MAX_ATTEMPTS:
            self.verification_timer.stop()
            self._verification_attempts = 0
            styled_message_box(
                self.parent(), "Timeout",
                f"No se pudieron verificar los archivos de:\n"
                f"{self.last_in_queue['artist']} - {self.last_in_queue['song']}\n\n"
                "Verifique manualmente la carpeta separated/",
                QMessageBox.Icon.Warning,
            )
            return

        if not self.last_in_queue.get('artist') or not self.last_in_queue.get('song'):
            self.verification_timer.stop()
            self._verification_attempts = 0
            return

        folder = self._song_folder(self.last_in_queue['artist'],
                                   self.last_in_queue['song'])
        base = folder / "separated"
        required = ['drums.mp3', 'vocals.mp3', 'bass.mp3', 'other.mp3']

        if not base.exists() or not all((base / f).exists() for f in required):
            self._verification_attempts += 1
            return

        self.verification_timer.stop()
        self._verification_attempts = 0
        self.song_ready.emit(folder)

    def _song_folder(self, artist: str, song: str) -> Path:
        # Mismo saneado que usó DemucsWorker para crear la carpeta: con los
        # nombres crudos, un artista tipo "AC/DC" nunca se encontraría.
        return (self.library / _sanitize_path_component(artist)
                / _sanitize_path_component(song))
