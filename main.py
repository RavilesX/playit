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

    # Splash rápido
    from PyQt6.QtWidgets import QSplashScreen
    splash = QSplashScreen(QPixmap(resource_path("images/main_window/splash.png")))
    splash.showMessage("Cargando…", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    splash.show()

    QTimer.singleShot(100, create_player)  # ventana aparece casi instantly
    sys.exit(app.exec())