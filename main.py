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
os.environ["TORCH_LOAD_WEIGHTS_ONLY"] = "0"
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap
from audio_player import AudioPlayer
from resources import resource_path


def create_player():
    global player
    player = AudioPlayer()
    player.show()
    splash.finish(player)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    from PyQt6.QtWidgets import QSplashScreen
    splash = QSplashScreen(QPixmap(resource_path("images/main_window/splash.png")))
    splash.showMessage(
        "Cargando…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
        Qt.GlobalColor.white,
    )
    splash.show()

    QTimer.singleShot(100, create_player)
    sys.exit(app.exec())
