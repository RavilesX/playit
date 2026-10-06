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
from PyQt6.QtCore import QLibraryInfo, QTimer, QTranslator, Qt
from PyQt6.QtGui import QPixmap
from audio_player import AudioPlayer
from resources import load_app_fonts, resource_path
from platform_utils import configure_logging
from i18n import detect_system_language, load_language, tr
from settings import load_settings

configure_logging()


def create_player():
    global player
    player = AudioPlayer()
    player.show()
    splash.finish(player)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Antes de cualquier QSS: estilos.css pide "Saira Stencil One" por nombre.
    load_app_fonts()
    # Idioma elegido, o el del sistema (inglés si no es es/pt/en). Antes de
    # construir cualquier widget: la UI se arma una sola vez.
    lang = load_language(load_settings().get("language") or detect_system_language())
    # Textos propios de Qt (Yes/No/Cancel, menú contextual, diálogos de archivo).
    qt_translator = QTranslator()
    qt_name = "qtbase_pt_BR" if lang == "pt" else f"qtbase_{lang}"  # Qt solo trae pt_BR
    if qt_translator.load(qt_name, QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_translator)

    from PyQt6.QtWidgets import QSplashScreen
    splash = QSplashScreen(QPixmap(resource_path("images/main_window/splash.png")))
    splash.showMessage(
        tr("Cargando…"),
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
        Qt.GlobalColor.white,
    )
    splash.show()

    QTimer.singleShot(100, create_player)
    sys.exit(app.exec())
