import sys
from PyQt6.QtWidgets import QApplication
from audio_player import AudioPlayer

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = AudioPlayer()
    player.show()
    sys.exit(app.exec())