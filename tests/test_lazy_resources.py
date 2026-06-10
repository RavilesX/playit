"""Tests de ResourceCache, LazyImageManager y LazyPlaylistLoader."""
import json
import time

from lazy_resources import ResourceCache, LazyImageManager, LazyPlaylistLoader


class TestResourceCache:
    def test_carga_una_sola_vez(self):
        cache = ResourceCache(max_size=5)
        calls = []

        def loader():
            calls.append(1)
            return "valor"

        assert cache.get("k", loader) == "valor"
        assert cache.get("k", loader) == "valor"
        assert len(calls) == 1

    def test_loader_con_error_devuelve_none(self):
        cache = ResourceCache(max_size=5)

        def boom():
            raise RuntimeError("x")

        assert cache.get("k", boom) is None

    def test_lru_desaloja_el_mas_viejo(self):
        cache = ResourceCache(max_size=2)
        cache.get("a", lambda: 1)
        time.sleep(0.01)
        cache.get("b", lambda: 2)
        time.sleep(0.01)
        cache.get("c", lambda: 3)
        cache._cleanup_if_needed()
        assert "a" not in cache._cache
        assert "b" in cache._cache and "c" in cache._cache

    def test_remove_y_clear(self):
        cache = ResourceCache(max_size=5)
        cache.get("a", lambda: 1)
        cache.remove("a")
        assert "a" not in cache._cache
        cache.get("a", lambda: 1)
        cache.clear()
        assert not cache._cache


class TestLazyImageManager:
    def test_portada_inexistente_usa_default(self, app, tmp_path):
        mgr = LazyImageManager()
        image = mgr.load_cover_lazy(tmp_path, (100, 100))
        assert image is not None
        assert not image.isNull()

    def test_portada_desde_cover_png(self, app, tmp_path):
        from PyQt6.QtGui import QImage
        src = QImage(80, 80, QImage.Format.Format_RGB32)
        src.fill(0xFF0000)
        src.save(str(tmp_path / "cover.png"))

        mgr = LazyImageManager()
        image = mgr.load_cover_lazy(tmp_path, (100, 100))
        assert not image.isNull()
        assert image.width() <= 100


class TestLazyPlaylistLoader:
    def test_emite_lotes_y_finished(self, qtbot, tmp_path):
        for i in range(3):
            d = tmp_path / f"song{i}"
            d.mkdir()
            (d / "data.json").write_text(
                json.dumps({f"Artista{i}": {f"Cancion{i}": {"path": "x"}}}),
                encoding="utf-8",
            )

        loader = LazyPlaylistLoader()
        received = []
        loader.playlist_batch_updated.connect(received.extend)

        with qtbot.waitSignal(loader.loading_finished, timeout=5000):
            loader.load_playlist_lazy(tmp_path)

        assert len(received) == 3
        artists = {s["artist"] for s in received}
        assert artists == {"Artista0", "Artista1", "Artista2"}

    def test_carpeta_vacia_emite_finished(self, qtbot, tmp_path):
        loader = LazyPlaylistLoader()
        with qtbot.waitSignal(loader.loading_finished, timeout=5000):
            loader.load_playlist_lazy(tmp_path)
