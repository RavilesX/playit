"""_stream_writer decodifica los stems por bloques (sin cargarlos enteros):
mezcla, respeta mute y posición de inicio, y termina o se detiene en limpio."""
import threading

import numpy as np
import soundfile as sf

from audio_player import TRACK_NAMES

SR = 8000
FRAMES = 5000  # no múltiplo de 1024: el último bloque llega corto


class FakeStream:
    def __init__(self):
        self.chunks = []

    def write(self, chunk):
        self.chunks.append(chunk.copy())


def _stems(tmp_path):
    """Una pista por stem con amplitud distinta para poder separarlas."""
    rng = np.random.default_rng(0)
    paths, datas = [], []
    for i, track in enumerate(TRACK_NAMES):
        data = (rng.uniform(-1, 1, (FRAMES, 2)) * 0.1 * (i + 1)).astype("float32")
        path = tmp_path / f"{track}.wav"
        sf.write(path, data, SR, subtype="FLOAT")
        paths.append(path)
        datas.append(data)
    return paths, datas


def _run(player, monkeypatch, paths, start=0):
    scheduled = []
    monkeypatch.setattr(player, "play_next", lambda: scheduled.append("next"))
    monkeypatch.setattr(player, "stop_playback", lambda: scheduled.append("stop"))
    monkeypatch.setattr(player, "_repeat", False)
    monkeypatch.setattr(player, "volume", 100)
    monkeypatch.setattr(player, "auto_unmute_enabled", False)
    # `player` es de sesión: otros tests dejan volúmenes y ganancia residual
    monkeypatch.setattr(player, "individual_volumes", {t: 1.0 for t in TRACK_NAMES})
    monkeypatch.setattr(player, "_auto_unmute_gain", 0.0)
    player._sr = SR
    player._stream_pause_flag.set()
    stream = FakeStream()
    player._stream_writer(stream, paths, start, threading.Event())
    out = np.concatenate(stream.chunks) if stream.chunks else np.zeros((0, 2))
    return out, scheduled


def _wait_scheduled(qtbot, scheduled):
    # El writer agenda el siguiente paso con QTimer.singleShot(0, ...)
    qtbot.waitUntil(lambda: bool(scheduled), timeout=1000)


def test_mezcla_todo_y_avanza_al_terminar(player, tmp_path, monkeypatch, qtbot):
    paths, datas = _stems(tmp_path)
    out, scheduled = _run(player, monkeypatch, paths)
    assert np.allclose(out, sum(datas), atol=1e-6)
    _wait_scheduled(qtbot, scheduled)
    assert scheduled == ["next"]
    assert player._seek_position == FRAMES


def test_pista_muteada_no_suena_pero_sigue_sincronizada(player, tmp_path, monkeypatch):
    paths, datas = _stems(tmp_path)
    monkeypatch.setitem(player.mute_states, "vocals", True)
    out, _ = _run(player, monkeypatch, paths, start=1500)
    expected = datas[0] + datas[2] + datas[3]
    assert np.allclose(out, expected[1500:], atol=1e-6)


def test_stem_ilegible_detiene_sin_avanzar(player, tmp_path, monkeypatch, qtbot):
    paths, _ = _stems(tmp_path)
    paths[2] = tmp_path / "no_existe.wav"
    out, scheduled = _run(player, monkeypatch, paths)
    assert len(out) == 0
    _wait_scheduled(qtbot, scheduled)
    assert scheduled == ["stop"]
