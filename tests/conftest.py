"""Configuración común de tests.

Los tests corren headless (QT_QPA_PLATFORM=offscreen) y NO requieren
audio ni red. AudioPlayer se instancia una sola vez por sesión porque
su __init__ construye toda la UI.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Los módulos viven en la raíz del repo
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture(scope="session")
def app():
    from PyQt6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(scope="session")
def player(app):
    from audio_player import AudioPlayer
    p = AudioPlayer()
    yield p
    p._control_channels('stop')


@pytest.fixture(autouse=True)
def clean_playlist(request):
    """Deja la playlist vacía antes de cada test que use `player`."""
    if "player" in request.fixturenames:
        p = request.getfixturevalue("player")
        p.playlist.clear()
        p._playlist_keys.clear()
        p.playlist_widget.clear()
        p.current_index = -1
    yield
