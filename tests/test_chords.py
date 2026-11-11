"""Acordes: archivo chords.json, capa de teoría y carrusel."""
import json

import pytest

from chords import (CHORDS_FILE, chord_index_at, estimate_key, format_chord,
                    format_key, postprocess, read_chords, reduce_label, spell,
                    write_chords)


# ── Archivo ──────────────────────────────────────────────────────────────
def test_write_read_roundtrip(tmp_path):
    data = {"engine": "test", "key": "G", "mode": "major", "duration": 10.0,
            "chords": [[0.0, "G"], [2.5, "C"], [5.0, "D"]]}
    write_chords(tmp_path, data)
    got = read_chords(tmp_path)
    assert got["v"] == 1
    assert got["chords"] == data["chords"]
    assert got["key"] == "G"
    assert not (tmp_path / "chords.json.tmp").exists()


def test_read_missing_and_corrupt(tmp_path):
    assert read_chords(tmp_path) == {}
    (tmp_path / CHORDS_FILE).write_text("{roto", encoding="utf-8")
    assert read_chords(tmp_path) == {}
    (tmp_path / CHORDS_FILE).write_text("[1, 2]", encoding="utf-8")
    assert read_chords(tmp_path) == {}


def test_read_drops_bad_entries_and_sorts(tmp_path):
    (tmp_path / CHORDS_FILE).write_text(json.dumps({"chords": [
        [5.0, "D"], ["x", "C"], [1.0], [-1, "E"], [0.0, "G"], [2.0, ""], "basura",
    ]}), encoding="utf-8")
    assert read_chords(tmp_path)["chords"] == [[0.0, "G"], [5.0, "D"]]


@pytest.mark.parametrize("t, expected", [
    (-0.1, -1), (0.0, 0), (2.49, 0), (2.5, 1), (4.99, 1), (5.0, 2), (999, 2),
])
def test_chord_index_at_edges(t, expected):
    assert chord_index_at([0.0, 2.5, 5.0], t) == expected


def test_chord_index_at_empty():
    assert chord_index_at([], 3.0) == -1


# ── Etiquetas ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, expected", [
    ("C", (0, "")), ("C:maj", (0, "")), ("C:maj7", (0, "")), ("G:7", (7, "")),
    ("A:min", (9, "m")), ("A:min7", (9, "m")), ("E:minmaj7", (4, "m")),
    ("B:dim", (11, "dim")), ("B:hdim7", (11, "dim")), ("C:aug", (0, "aug")),
    ("D:sus4", (2, "sus")), ("Db:min", (1, "m")), ("C#:min", (1, "m")),
    ("F:maj/3", (5, "")), ("G:7(b9)", (7, "")), ("F#m", (6, "m")),
    ("N", None), ("X", None), ("", None), ("H:min", None),
])
def test_reduce_label(raw, expected):
    assert reduce_label(raw) == expected


def test_spell_follows_key():
    assert spell(10, "", 5, "major") == "Bb"    # Fa mayor: bemoles
    assert spell(6, "m", 7, "major") == "F#m"   # Sol mayor: sostenidos
    assert spell(10, "", 0, "major") == "Bb"    # Do mayor: bVII
    assert spell(6, "", 0, "major") == "F#"     # Do mayor: II/V con #
    assert spell(3, "m", 0, "minor") == "Ebm"   # Do menor = relativo de Mib
    assert spell(1, "", None) == "C#"


def test_format_chord_notations():
    assert format_chord("F#m") == "F#m"
    assert format_chord("F#m", "latin") == "Fa#m"
    assert format_chord("Bb", "latin") == "Sib"
    assert format_chord("G", "latin") == "Sol"
    assert format_chord("Bdim", "latin") == "Sidim"
    assert format_chord("N") == "—"
    assert format_key("E", "minor", "latin") == "Mim"
    assert format_key("", "major") == ""


# ── Teoría ───────────────────────────────────────────────────────────────
def test_estimate_key_major_progression():
    # I-IV-V-I en Sol mayor
    segs = [(4, 7, ""), (2, 0, ""), (2, 2, ""), (4, 7, ""), (1, 4, "m")]
    assert estimate_key(segs) == (7, "major")


def test_estimate_key_minor_progression():
    # i-iv-V-i en La menor, con la tónica dominando
    segs = [(6, 9, "m"), (2, 2, "m"), (2, 4, ""), (6, 9, "m")]
    assert estimate_key(segs) == (9, "minor")


def _frames(*parts, conf=0.9):
    """`("G", 20), ("C", 3)` → lista de cuadros (etiqueta, confianza)."""
    out = []
    for label, n in parts:
        out += [(label, conf)] * n
    return out


def test_postprocess_basic_progression():
    hop = 0.1
    frames = _frames(("N", 10), ("G:maj", 40), ("C:maj7", 30), ("D:7", 30), ("G", 40))
    res = postprocess(frames, hop, 15.0)
    assert res["key"] == "G" and res["mode"] == "major"
    assert [c[1] for c in res["chords"]] == ["N", "G", "C", "D", "G"]
    assert res["chords"][1][0] == pytest.approx(1.0)
    assert res["duration"] == 15.0


def test_postprocess_merges_short_flicker():
    # 0.2 s de Em en medio de G: parpadeo, se funde (comparten dos notas)
    frames = _frames(("G", 30), ("E:min", 2), ("G", 30), ("C", 30))
    labels = [c[1] for c in postprocess(frames, 0.1, 9.2)["chords"]]
    assert labels == ["G", "C"]


def test_postprocess_nondiatonic_short_and_unsure_is_merged():
    frames = (_frames(("G", 30)) + _frames(("Ab", 6), conf=0.3)
              + _frames(("G", 30), ("C", 20), ("D", 20)))
    labels = [c[1] for c in postprocess(frames, 0.1, 10.6)["chords"]]
    assert "G#" not in labels and "Ab" not in labels


def test_postprocess_nondiatonic_long_is_kept():
    # bVII (Fa en Sol mayor) largo: acorde prestado, se respeta
    frames = _frames(("G", 40), ("C", 20), ("F", 20), ("G", 40), ("D", 20))
    labels = [c[1] for c in postprocess(frames, 0.1, 14.0)["chords"]]
    assert "F" in labels


def test_postprocess_sus_takes_degree_quality():
    # A:sus4 en Sol mayor = grado ii → menor
    frames = _frames(("G", 40), ("C", 20), ("A:sus4", 20), ("D", 20), ("G", 40))
    labels = [c[1] for c in postprocess(frames, 0.1, 14.0)["chords"]]
    assert "Am" in labels


def test_postprocess_empty():
    res = postprocess([], 0.1, 3.0)
    assert res["chords"] == [] and res["key"] == ""


# ── Carrusel ─────────────────────────────────────────────────────────────
@pytest.fixture
def carousel(app):
    from PyQt6.QtWidgets import QWidget
    from ui_components import ChordCarouselWidget
    parent = QWidget()
    parent.resize(800, 500)
    w = ChordCarouselWidget(parent)
    parent.show()  # sin show, Qt difiere los Resize hasta mostrar
    w.set_chords({"key": "G", "mode": "major", "duration": 12.0,
                  "chords": [[0.0, "N"], [2.0, "G"], [6.0, "C"], [9.0, "D"]]})
    yield w
    parent.deleteLater()


def test_carousel_slots_follow_time(carousel):
    carousel.set_time(0.5)
    assert carousel.labels_at_current() == ("", "—", "G")
    carousel.set_time(4.0)
    assert carousel.labels_at_current() == ("—", "G", "C")
    assert carousel.progress() == pytest.approx(0.5)
    carousel.set_time(10.5)
    assert carousel.labels_at_current() == ("C", "D", "")
    assert carousel.progress() == pytest.approx(0.5)


def test_carousel_seek_back_and_notation(carousel):
    carousel.set_time(10.0)
    carousel.set_time(3.0)  # seek hacia atrás: sin estado pegado
    carousel.set_notation("latin")
    assert carousel.labels_at_current() == ("—", "Sol", "Do")


def test_carousel_scales_with_parent(carousel):
    parent = carousel.parentWidget()
    small = carousel.height()
    parent.resize(1600, 1000)
    assert carousel.height() > small
    assert carousel.x() == carousel.MARGIN


def test_player_shows_carousel_only_with_chords(player, tmp_path, monkeypatch):
    # No tocar el settings.json real
    monkeypatch.setattr("audio_player.save_setting", lambda *a: None)
    folder = tmp_path / "song"
    folder.mkdir()
    player.playlist.append({"artist": "A", "song": "S", "path": str(folder)})
    player.current_index = 0
    player._chords_enabled = True
    player._load_chords()
    assert player.chord_carousel.isHidden()

    write_chords(folder, {"key": "C", "mode": "major", "duration": 4.0,
                          "chords": [[0.0, "C"], [2.0, "G"]]})
    player._load_chords()
    assert not player.chord_carousel.isHidden()
    assert player._chords_timer.isActive()

    player._toggle_chords(False)
    assert player.chord_carousel.isHidden()
    assert not player._chords_timer.isActive()
    player._toggle_chords(True)

    player.stop_playback()
    assert player.chord_carousel.isHidden()


def test_force_detect_reports_result_once(player, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QListWidgetItem
    from ui_components import PlaylistItemDelegate
    msgs = []
    monkeypatch.setattr(player, "show_status_message", lambda t, *a: msgs.append(t))
    monkeypatch.setattr(player._chords_queue, "put", lambda *a, **k: None)
    item = QListWidgetItem()
    item.setData(PlaylistItemDelegate.PATH_ROLE, str(tmp_path))

    player._force_detect_chords(item)
    player._on_chords_ready(str(tmp_path), False)
    player._on_chords_ready(str(tmp_path), True)  # automática: sin aviso
    assert msgs == ["Detectando acordes…", "No se pudieron detectar acordes"]


# ── Motor ────────────────────────────────────────────────────────────────
import numpy as np  # noqa: E402

import chords as ch  # noqa: E402


def test_vocab_matches_model_contract():
    assert len(ch.VOCAB) == 170
    assert ch.VOCAB[:3] == ("C:min", "C", "C:dim")
    assert ch.VOCAB[-2:] == ("X", "N")
    # Todo el vocabulario del modelo se reduce sin errores
    for label in ch.VOCAB[:-2]:
        assert ch.reduce_label(label) is not None


@pytest.mark.parametrize("n", [1000, 1001, 10333439 // 1000])  # incluye longitud prima
def test_resample_length_and_tone(n):
    sr = 44100
    t = np.arange(n) / sr
    y = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = ch._resample(y, 1, 2)
    assert len(out) == -(-n // 2)
    if n > 5000:  # amplitud conservada (sin el ×√2 de _halve)
        assert np.abs(out[100:-100]).max() == pytest.approx(1.0, abs=0.02)


def test_cqt_peaks_at_the_played_note():
    sr = ch.CQT_SR
    t = np.arange(sr * 4) / sr
    y = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)  # La4
    feats = ch.cqt_features(y)
    assert feats.shape[1] == 144
    assert len(feats) == 1 + (len(y) // 2) // (ch.CQT_HOP // 2)
    # La4 está 3 octavas y 9 semitonos sobre Do1 → 45 semitonos → bin 90
    mid = feats[len(feats) // 2]
    assert int(mid.argmax()) == 90


def test_cqt_matches_librosa():
    librosa = pytest.importorskip("librosa")
    rng = np.random.default_rng(0)
    sr = ch.CQT_SR
    t = np.arange(sr * 6) / sr
    y = sum(np.sin(2 * np.pi * f * t) for f in (98.0, 246.9, 392.0, 587.3))
    y = (y + 0.05 * rng.standard_normal(len(t))).astype(np.float32)
    ref = np.log(np.abs(librosa.cqt(y, sr=sr, hop_length=ch.CQT_HOP, fmin=ch.CQT_FMIN,
                                    n_bins=144, bins_per_octave=24)) + 1e-6).T
    mine = ch.cqt_features(y)
    assert mine.shape == ref.shape
    assert np.median(np.abs(mine - ref)) < 0.01


needs_engine = pytest.mark.skipif(not ch.chords_available(),
                                  reason="sin onnxruntime o sin modelo")


@needs_engine
def test_run_model_shapes_across_window_groups():
    for t in (5, 108, 108 * 16 + 3):
        out = ch.run_model(np.full((t, 144), -5.0, np.float32))
        assert out.shape == (t, 170)
        assert np.isfinite(out).all()


def _write_stems(folder, freqs_per_section, sr=44100, section_s=4.0):
    import soundfile as sf
    sep = folder / "separated"
    sep.mkdir(parents=True)
    t = np.arange(int(sr * section_s)) / sr
    other = np.concatenate([
        sum(np.sin(2 * np.pi * f * t) * 0.2 for f in fs) for fs in freqs_per_section])
    bass = np.concatenate([np.sin(2 * np.pi * fs[0] / 2 * t) * 0.3
                           for fs in freqs_per_section])
    sf.write(sep / "other.mp3", np.stack([other, other], 1), sr)
    sf.write(sep / "bass.mp3", np.stack([bass, bass], 1), sr)


@needs_engine
def test_detect_and_ensure_chords(tmp_path):
    # Do mayor (C4 E4 G4) y luego Sol mayor (G3 B3 D4): acordes de órgano
    _write_stems(tmp_path, [(261.6, 329.6, 392.0), (196.0, 246.9, 293.7)])
    assert ch.ensure_chords(tmp_path) is True
    data = ch.read_chords(tmp_path)
    assert data["engine"] == ch.ENGINE_NAME
    assert data["source"] == ["bass", "other"]
    assert data["duration"] == pytest.approx(8.0, abs=0.1)
    labels = [c[1] for c in data["chords"]]
    assert "C" in labels and "G" in labels
    assert labels.index("C") < labels.index("G")

    # Sin force no pisa (correcciones a mano); con force sí
    (tmp_path / CHORDS_FILE).write_text('{"chords": [[0, "Am"]]}', encoding="utf-8")
    assert ch.ensure_chords(tmp_path) is False
    assert read_chords(tmp_path)["chords"] == [[0.0, "Am"]]
    assert ch.ensure_chords(tmp_path, force=True) is True


def test_chords_queue_tries_once_unless_forced(tmp_path, monkeypatch):
    import threading
    calls, done = [], threading.Event()

    def fake_ensure(folder, force=False):
        calls.append((folder, force))
        return True

    monkeypatch.setattr(ch, "ensure_chords", fake_ensure)
    results = []

    def on_done(folder, ok):
        results.append((folder, ok))
        if len(results) == 2:
            done.set()

    q = ch.ChordsQueue(on_done)
    q.put(tmp_path)
    q.put(tmp_path)              # repetido: se ignora
    q.put(tmp_path, force=True)  # forzado: sí
    assert done.wait(5)
    assert calls == [(str(tmp_path), False), (str(tmp_path), True)]
    assert results == [(str(tmp_path), True)] * 2
