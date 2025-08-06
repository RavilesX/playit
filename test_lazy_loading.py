import sys
import time
from PyQt6.QtWidgets import QApplication
from main import AudioPlayer


def test_basic_functionality():
    app = QApplication(sys.argv)
    player = AudioPlayer()

    # Test 1: Verificar que los gestores se inicializaron
    assert hasattr(player, 'lazy_audio')
    assert hasattr(player, 'lazy_images')
    assert hasattr(player, 'lazy_lyrics')
    print("✅ Gestores de lazy loading inicializados correctamente")

    # Test 2: Verificar cache funcional
    cache_stats = player.get_cache_stats()
    assert isinstance(cache_stats, dict)
    print("✅ Sistema de cache funcionando")

    player.show()
    print("✅ Aplicación inicia correctamente con lazy loading")

    return player, app


if __name__ == "__main__":
    player, app = test_basic_functionality()
    #app.exec()  # Descomenta para probar la UI