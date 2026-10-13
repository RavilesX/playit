"""Flujo de instalación de DependencyManager sin AudioPlayer: ya-instalado,
guards y arranque del worker (reemplazado por uno falso, sin subprocesos)."""
import os
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

import dependencies
import platform_utils
from dependencies import DependencyManager


class FakeWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        self.finished.emit()


class FailingWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        self.error.emit("boom")  # como BaseInstallWorker: error y nada más


@pytest.fixture
def boxes(monkeypatch):
    """Registra los títulos de cada diálogo y confirma siempre con Sí."""
    shown = []

    def fake_box(parent, title, *args, **kwargs):
        shown.append(title)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(dependencies, "styled_message_box", fake_box)
    return shown


@pytest.fixture
def deps(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    mgr = DependencyManager(parent)
    monkeypatch.setattr(dependencies, "DemucsInstallWorker", FakeWorker)
    monkeypatch.setattr(mgr, "check_demucs", lambda: None)  # sin subproceso
    yield mgr  # yield, no return: si `parent` sale de alcance Qt borra también a mgr


@pytest.mark.parametrize("returncode, esperado", [(0, True), (9009, False)])
def test_check_python_ejecuta_el_comando(monkeypatch, returncode, esperado):
    """9009 es lo que devuelve el alias de la Microsoft Store en Windows:
    existe en el PATH pero no es Python."""
    monkeypatch.setattr(platform_utils, "run_silent",
                        lambda *a, **k: SimpleNamespace(returncode=returncode))
    assert platform_utils.check_python() is esperado


def test_merge_path_registro_primero_sin_repetidos():
    sep = os.pathsep
    merged = platform_utils._merge_path(f"py{sep}apps", f"apps{sep}extra")
    assert merged == sep.join(["py", "apps", "extra"])


def test_ya_instalado_no_arranca_worker(deps, boxes):
    deps.demucs_available = True
    deps.install_demucs()
    assert boxes == ["Demucs ya instalado"]
    assert not deps._running


def test_guard_python_bloquea(deps, boxes):
    deps.demucs_available = False
    deps.python_available = False
    deps.install_demucs()
    assert boxes == ["Python requerido"]
    assert not deps._running


def test_instalacion_exitosa(deps, boxes, qtbot):
    deps.demucs_available = False
    deps.python_available = True
    with qtbot.waitSignal(deps.changed, timeout=3000):
        deps.install_demucs()
        assert deps.demucs_install_in_progress
    assert deps.demucs_available
    assert not deps.demucs_install_in_progress
    assert boxes == ["Confirmar instalación", "Instalación completada"]


def test_instalacion_fallida_termina_el_hilo(deps, boxes, qtbot, monkeypatch):
    """Un worker que falla debe soltar su QThread: si quedaba corriendo, el
    reintento pisaba la referencia en `_running` y Qt abortaba la app."""
    monkeypatch.setattr(dependencies, "DemucsInstallWorker", FailingWorker)
    deps.demucs_available = False
    deps.python_available = True
    with qtbot.waitSignal(deps.op_finished, timeout=3000):
        deps.install_demucs()
    thread = deps._running["Demucs"][0]

    def terminado():
        try:
            return thread.isFinished()
        except RuntimeError:  # ya borrado por deleteLater
            return True

    qtbot.waitUntil(terminado, timeout=3000)
    assert not deps.demucs_available
