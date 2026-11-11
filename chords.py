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

"""Acordes de una canción: archivo `chords.json` y reglas de teoría musical.

Sin Qt (como `lyrics_api.py`): el motor de detección corre en hilos de fondo
y la UI solo consume `read_chords` / `chord_index_at` / `format_chord`.

Motor (`detect_chords`): ChordNet "2E1D" de ChordMini (MIT) exportado a ONNX,
sobre `bass + other`. `onnxruntime` es opcional y de import perezoso: sin él,
`chords_available()` es falso y la feature se apaga sola. La CQT que espera
el modelo NO viene en el grafo: `cqt_features` replica la de librosa 0.11.0
en numpy (mismo esquema de octavas), cambiando solo el remuestreador.

`chords.json` vive junto a `lyrics.lrc`:
    {"v": 1, "engine": "...", "source": ["bass", "other"],
     "key": "G", "mode": "major", "duration": 215.3,
     "chords": [[0.0, "N"], [1.86, "G"], [5.57, "C"]]}

Cada entrada es [segundo de inicio, etiqueta]; un acorde termina donde empieza
el siguiente y el último en `duration`. Las etiquetas van en notación
americana y ya con la ortografía de la tonalidad ("Bb" en Fa mayor); la
notación latina es solo de pantalla (`format_chord`). "N" = sin acorde.

`postprocess` es la capa de teoría, común a cualquier motor: recibe la salida
cruda por cuadro y devuelve la lista final reducida a lo básico.
"""
import bisect
import json
import logging
import os
import queue
import re
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

CHORDS_FILE = "chords.json"
FORMAT_VERSION = 1
NO_CHORD = "N"

# ── Umbrales de la capa de teoría (se afinan en la Fase 0 del plan) ──────
# Segmentos más cortos que esto se funden con un vecino: evita parpadeo.
MIN_SEGMENT_S = 0.4
# Un acorde fuera de la tonalidad se respeta (acorde prestado, dominante
# secundaria) si dura al menos esto o si el motor está seguro de él.
NONDIATONIC_MIN_S = 1.0
NONDIATONIC_MIN_CONF = 0.6

_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
# Do mayor / La menor: sin armadura, se escriben los cromatismos más comunes
# en la práctica (bVII, bIII, bVI y los dominantes secundarios con #).
_NATURAL_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_LATIN = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Tónicas (del relativo mayor) cuya armadura lleva bemoles
_FLAT_KEYS = {5, 10, 3, 8, 1, 6}  # F Bb Eb Ab Db Gb

# Calidades de salida: tríadas. Intervalos para el histograma de tonalidad.
_TRIAD = {"": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8)}
# Calidad de cada grado de la escala mayor (semitonos sobre la tónica)
_MAJOR_DEGREES = {0: "", 2: "m", 4: "m", 5: "", 7: "", 9: "m", 11: "dim"}

# Perfiles de Krumhansl-Kessler
_KK_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_KK_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


# ──────────────────────────────────────────────────────────────────────────
# ── Archivo ──────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────
def read_chords(folder) -> dict:
    """Contenido de `chords.json`, o `{}` si falta o está corrupto.

    Nunca lanza: se llama al reproducir. Descarta entradas mal formadas en vez
    de rechazar el archivo entero (puede venir editado a mano) y garantiza
    `chords` ordenada por tiempo.
    """
    path = Path(folder) / CHORDS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("chords.json ilegible en %s: %s", folder, e)
        return {}
    if not isinstance(data, dict):
        return {}
    chords = []
    for entry in data.get("chords") or []:
        try:
            t, label = float(entry[0]), str(entry[1])
        except (TypeError, ValueError, IndexError):
            continue
        if t >= 0 and label:
            chords.append([t, label])
    chords.sort(key=lambda c: c[0])
    data["chords"] = chords
    return data


def write_chords(folder, data: dict) -> None:
    """Escribe `chords.json` de forma atómica (tmp + replace): un corte a
    medias dejaría un JSON roto que `read_chords` descartaría entero."""
    path = Path(folder) / CHORDS_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"v": FORMAT_VERSION, **data}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def chord_index_at(starts: list, t: float) -> int:
    """Índice del acorde que suena en `t` segundos, -1 antes del primero.

    Sin estado: un salto de posición (seek) no necesita nada especial.
    """
    return bisect.bisect_right(starts, t) - 1


# ──────────────────────────────────────────────────────────────────────────
# ── Etiquetas ────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────
_LABEL_RE = re.compile(r"^([A-G])([#b]*)(.*)$")


def parse_label(label: str):
    """`"F#m"` → `(6, "m")`. `None` para "sin acorde" o algo ilegible."""
    m = _LABEL_RE.match(label.strip())
    if not m:
        return None
    root = (_PC[m.group(1)] + m.group(2).count("#") - m.group(2).count("b")) % 12
    quality = m.group(3)
    return (root, quality) if quality in _TRIAD else None


def reduce_label(raw: str):
    """Etiqueta cruda del motor → `(raíz, calidad)` de tríada, o `None`.

    Acepta la sintaxis de Harte que usan los modelos (`"C#:min7"`,
    `"Bb:sus4"`, `"A:hdim7"`, `"G"`, `"N"`, `"X"`) y también la corta
    (`"F#m"`). Séptimas, sextas, novenas y extensiones caen a su tríada;
    `sus` se devuelve como calidad `"sus"` para que `postprocess` le asigne
    la del grado según la tonalidad (no tiene tercera que la decida).
    """
    raw = raw.strip()
    if not raw or raw in ("N", "X"):
        return None
    if ":" not in raw:
        return parse_label(raw)
    root_s, _, qual = raw.partition(":")
    parsed = parse_label(root_s)
    if parsed is None:
        return None
    root = parsed[0]
    qual = qual.split("/")[0].split("(")[0]  # inversión y notas añadidas fuera
    if qual.startswith(("hdim", "dim")):
        return root, "dim"
    if qual.startswith("aug"):
        return root, "aug"
    if qual.startswith("sus"):
        return root, "sus"
    if qual.startswith("min"):  # min, min7, minmaj7, min6...
        return root, "m"
    return root, ""  # maj, maj7, 7, 9, 6, 13, vacío...


def spell(root: int, quality: str, key_tonic: int | None = None,
          key_mode: str = "major") -> str:
    """Nombre del acorde con la ortografía de la tonalidad."""
    names = _SHARP_NAMES
    if key_tonic is not None:
        major_tonic = key_tonic if key_mode == "major" else (key_tonic + 3) % 12
        if major_tonic == 0:
            names = _NATURAL_NAMES
        elif major_tonic in _FLAT_KEYS:
            names = _FLAT_NAMES
    return names[root % 12] + quality


def format_chord(label: str, notation: str = "american") -> str:
    """Texto de pantalla: `"N"` → `"—"`; en latina `"F#m"` → `"Fa#m"`."""
    if not label or label == NO_CHORD:
        return "—"
    if notation != "latin":
        return label
    m = _LABEL_RE.match(label)
    if not m:
        return label
    return _LATIN[m.group(1)] + m.group(2) + m.group(3)


def format_key(key: str, mode: str, notation: str = "american") -> str:
    """`("G", "major")` → `"G"`; `("E", "minor")` → `"Em"` (o `"Mim"`)."""
    if not key:
        return ""
    return format_chord(key + ("m" if mode == "minor" else ""), notation)


# ──────────────────────────────────────────────────────────────────────────
# ── Teoría musical ───────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────
def estimate_key(segments: list) -> tuple[int, str] | tuple[None, str]:
    """Tonalidad por correlación de Krumhansl sobre las notas de los acordes,
    ponderadas por duración. `segments`: `[(dur, raíz, calidad), ...]`."""
    hist = [0.0] * 12
    for dur, root, quality in segments:
        if root is None:
            continue
        for iv in _TRIAD.get(quality, _TRIAD[""]):
            hist[(root + iv) % 12] += dur
    if not any(hist):
        return None, "major"

    def corr(profile, k):
        p = [profile[(i - k) % 12] for i in range(12)]
        mh, mp = sum(hist) / 12, sum(p) / 12
        num = sum((h - mh) * (q - mp) for h, q in zip(hist, p))
        den = (sum((h - mh) ** 2 for h in hist) * sum((q - mp) ** 2 for q in p)) ** 0.5
        return num / den if den else 0.0

    best = max(((corr(prof, k), k, mode) for k in range(12)
                for mode, prof in (("major", _KK_MAJOR), ("minor", _KK_MINOR))))
    return best[1], best[2]


def diatonic_quality(root: int, key_tonic: int, key_mode: str) -> str | None:
    """Calidad que tiene `root` como grado de la tonalidad, o `None` si no
    pertenece a ella."""
    major_tonic = key_tonic if key_mode == "major" else (key_tonic + 3) % 12
    return _MAJOR_DEGREES.get((root - major_tonic) % 12)


def _similarity(a, b) -> int:
    """Notas en común entre dos acordes (para elegir con quién fundir)."""
    if a[0] is None or b[0] is None:
        return 0
    ta = {(a[0] + i) % 12 for i in _TRIAD.get(a[1], _TRIAD[""])}
    tb = {(b[0] + i) % 12 for i in _TRIAD.get(b[1], _TRIAD[""])}
    return len(ta & tb)


def postprocess(frames: list, hop_s: float, duration: float) -> dict:
    """Salida cruda por cuadro → datos listos para `write_chords`.

    `frames`: `[(etiqueta_cruda, confianza 0..1), ...]`, uno cada `hop_s`
    segundos. Pasos: reducir a tríadas → segmentar → estimar tonalidad →
    resolver `sus` → fundir segmentos cortos y cromatismos dudosos →
    escribir con la ortografía de la tonalidad.
    """
    # Segmentos [inicio, fin, raíz, calidad, suma_conf, n_cuadros]
    segs: list[list] = []
    for i, (raw, conf) in enumerate(frames):
        red = reduce_label(raw)
        root, quality = red if red else (None, "")
        t = i * hop_s
        if segs and segs[-1][2] == root and segs[-1][3] == quality:
            segs[-1][1] = t + hop_s
            segs[-1][4] += conf
            segs[-1][5] += 1
        else:
            segs.append([t, t + hop_s, root, quality, conf, 1])
    if not segs:
        return {"key": "", "mode": "major", "duration": duration, "chords": []}
    segs[-1][1] = max(segs[-1][1], duration)

    tonic, mode = estimate_key([(s[1] - s[0], s[2], s[3]) for s in segs])
    for s in segs:
        if s[3] == "sus":
            s[3] = (diatonic_quality(s[2], tonic, mode) if tonic is not None else "") or ""
            if s[3] == "dim":
                s[3] = ""

    def weak(s) -> bool:
        dur = s[1] - s[0]
        if dur < MIN_SEGMENT_S:
            return True
        if tonic is None or s[2] is None:
            return False
        outside = diatonic_quality(s[2], tonic, mode) != s[3]
        return (outside and dur < NONDIATONIC_MIN_S
                and s[4] / s[5] < NONDIATONIC_MIN_CONF)

    segs = _merge_weak(segs, weak)

    chords = []
    for s in segs:
        label = NO_CHORD if s[2] is None else spell(s[2], s[3], tonic, mode)
        if not chords or chords[-1][1] != label:
            chords.append([round(s[0], 3), label])
    return {
        "key": spell(tonic, "", tonic, mode) if tonic is not None else "",
        "mode": mode,
        "duration": round(duration, 3),
        "chords": chords,
    }


def _merge_weak(segs: list, weak) -> list:
    """Funde, del más corto al más largo, cada segmento débil con el vecino
    más parecido (más notas en común; a igualdad, el más largo)."""
    segs = [s[:] for s in segs]
    while len(segs) > 1:
        cands = [i for i, s in enumerate(segs) if weak(s)]
        if not cands:
            break
        i = min(cands, key=lambda j: segs[j][1] - segs[j][0])
        s = segs[i]
        neigh = [j for j in (i - 1, i + 1) if 0 <= j < len(segs)]
        j = max(neigh, key=lambda k: (_similarity((s[2], s[3]), (segs[k][2], segs[k][3])),
                                      segs[k][1] - segs[k][0]))
        n = segs[j]
        n[0], n[1] = min(n[0], s[0]), max(n[1], s[1])
        n[4] += s[4]
        n[5] += s[5]
        del segs[i]
        # El vecino absorbido puede ahora coincidir con el de su otro lado
        k = j - 1 if j > i else j
        for a in (k - 1, k):
            if 0 <= a < len(segs) - 1 and segs[a][2:4] == segs[a + 1][2:4]:
                segs[a][1] = segs[a + 1][1]
                segs[a][4] += segs[a + 1][4]
                segs[a][5] += segs[a + 1][5]
                del segs[a + 1]
                break
    return segs


# ──────────────────────────────────────────────────────────────────────────
# ── Motor: ChordNet (ChordMini) en ONNX ──────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────
ENGINE_NAME = "chordnet-onnx"
MODEL_FILE = "models/chordnet.onnx"
SOURCE_STEMS = ("bass", "other")

# Contrato del modelo (config.json del export ONNX): no cambiar sin reexportar
CQT_SR = 22050
CQT_HOP = 2048
CQT_FMIN = 32.70319566257483  # Do1
CQT_BINS = 144
CQT_BPO = 24
SEQ_LEN = 108
BATCH_WINDOWS = 16            # el grafo es estático: [16, 108, 144]
SMOOTH_FRAMES = 9
FRAME_S = CQT_HOP / CQT_SR    # ~93 ms

_VOCAB_ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_VOCAB_QUALITIES = ("min", "", "dim", "aug", "min6", "maj6", "min7", "minmaj7",
                    "maj7", "7", "dim7", "hdim7", "sus2", "sus4")
VOCAB = tuple(r if q == "" else f"{r}:{q}" for r in _VOCAB_ROOTS
              for q in _VOCAB_QUALITIES) + ("X", "N")

_session = None


def chords_available() -> bool:
    """True si hay `onnxruntime` y el modelo está en su sitio."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return _model_path().exists()


def _model_path() -> Path:
    from resources import resource_path
    return Path(resource_path(MODEL_FILE))


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        # Pocos hilos: corre mientras suena música y no debe robarle CPU
        # al hilo de audio (_stream_writer).
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3  # el export trae un inicializador sin uso que avisa
        _session = ort.InferenceSession(str(_model_path()), opts,
                                        providers=["CPUExecutionProvider"])
    return _session


def _is_smooth(n: int) -> bool:
    """True si `n` solo tiene factores 2, 3, 5 y 7 (FFT rápida)."""
    for p in (2, 3, 5, 7):
        while n % p == 0:
            n //= p
    return n == 1


def _resample(y: np.ndarray, num: int, den: int) -> np.ndarray:
    """Remuestreo ideal por FFT (pasa-bajos de pared) a `num/den` de la tasa;
    devuelve `ceil(len * num / den)` muestras, como librosa.

    Rellena con ceros hasta una longitud múltiplo de `den` y de factores
    chicos: con una longitud prima la FFT tardaba ~3.6 s en vez de ~0.2 s, y
    el relleno además evita que el final se mezcle circularmente con el
    principio. librosa usa soxr; para la CQT da lo mismo porque el bin más
    alto (~2 kHz) queda muy lejos de cualquier Nyquist de la cadena.
    """
    n = len(y)
    n_out = -(-n * num // den)
    m = -(-n // den)
    while not (_is_smooth(m * den) and _is_smooth(m * num)):
        m += 1
    n_pad, n_pad_out = m * den, m * num
    spec = np.fft.rfft(y, n=n_pad)
    keep = n_pad_out // 2 + 1
    if keep > len(spec):
        spec = np.concatenate([spec, np.zeros(keep - len(spec), spec.dtype)])
    out = np.fft.irfft(spec[:keep], n=n_pad_out)[:n_out]
    return (out * (num / den)).astype(np.float32)


def _halve(y: np.ndarray) -> np.ndarray:
    """Media tasa con `scale=True` de librosa (energía conservada: ×√2)."""
    return _resample(y, 1, 2) * np.float32(np.sqrt(2.0))


def _octave_basis(freqs: np.ndarray, sr: float, q: float):
    """FFT de los filtros de una octava, como `__vqt_filter_fft` de librosa:
    senoide compleja × Hann periódica, norma L1, centrada en n_fft."""
    lengths = q * sr / freqs
    n_fft = int(2 ** np.ceil(np.log2(lengths.max())))
    basis = np.zeros((len(freqs), n_fft), np.complex128)
    for i, (length, f) in enumerate(zip(lengths, freqs)):
        n = np.arange(-length // 2, length // 2)
        k = np.arange(len(n))
        sig = np.exp(2j * np.pi * f * n / sr) * (0.5 - 0.5 * np.cos(2 * np.pi * k / len(n)))
        sig /= np.abs(sig).sum()
        lpad = (n_fft - len(sig)) // 2
        basis[i, lpad:lpad + len(sig)] = sig * (length / n_fft)
    fft_basis = np.fft.fft(basis, axis=1)[:, : n_fft // 2 + 1]
    # Como librosa (sparsity=0.01): por fila, a cero los coeficientes más
    # chicos que suman el 1 % de la magnitud total.
    mag = np.abs(fft_basis)
    order = np.sort(mag, axis=1)
    cum = np.cumsum(order, axis=1) / order.sum(axis=1, keepdims=True)
    thresh = order[np.arange(len(mag)), np.argmin(cum < 0.01, axis=1)]
    fft_basis[mag < thresh[:, None]] = 0
    return fft_basis, n_fft


def cqt_features(y: np.ndarray) -> np.ndarray:
    """`log(|CQT| + 1e-6)` de `y` mono a 22050 Hz → `[T, 144]` float32.

    Mismo esquema que `librosa.cqt(sr=22050, hop_length=2048, fmin=C1,
    n_bins=144, bins_per_octave=24)` (tuning=0, scale=True): una bajada
    temprana a 11025 Hz y luego seis octavas, cada una a la mitad de tasa y
    de hop que la anterior, con FFT de 512 y la misma compensación de
    escalas. Respuesta final dividida por √(longitud del filtro a 22050).
    """
    freqs = CQT_FMIN * 2.0 ** (np.arange(CQT_BINS) / CQT_BPO)
    r2 = 2.0 ** (2 / CQT_BPO)
    q = (r2 + 1) / (r2 - 1)  # 1 / ancho de banda relativo
    n_oct = CQT_BINS // CQT_BPO

    y = _halve(y.astype(np.float32))  # bajada temprana
    sr, hop = CQT_SR / 2, CQT_HOP // 2
    resp = []
    for i in range(n_oct):
        if i:
            y = _halve(y)
            sr, hop = sr / 2, hop // 2
        top = CQT_BINS - CQT_BPO * i
        fft_basis, n_fft = _octave_basis(freqs[top - CQT_BPO:top], sr, q)
        # Compensación contra la tasa ORIGINAL (no la de tras la bajada
        # temprana): con 11025 aquí todo salía corrido log(√2).
        fft_basis *= np.sqrt(CQT_SR / sr)
        padded = np.pad(y, n_fft // 2)
        n_frames = 1 + len(y) // hop
        idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
        resp.append(np.fft.rfft(padded[idx], axis=1) @ fft_basis.T)  # [T, 24]
    t = min(len(r) for r in resp)
    cqt = np.concatenate([r[:t] for r in reversed(resp)], axis=1)
    lengths = q * CQT_SR / freqs
    return np.log(np.abs(cqt) / np.sqrt(lengths) + 1e-6).astype(np.float32)


def run_model(features: np.ndarray) -> np.ndarray:
    """Features `[T, 144]` → logits suavizados `[T, 170]`.

    Ventanas de 108 cuadros en grupos fijos de 16 (el grafo es estático);
    el relleno son ventanas en cero cuyos logits se descartan (las ventanas
    no interactúan dentro del modelo). Luego media móvil de 9 cuadros.
    """
    t = len(features)
    n_win = -(-t // SEQ_LEN)
    x = np.zeros((n_win * SEQ_LEN, CQT_BINS), np.float32)
    x[:t] = features
    x = x.reshape(n_win, SEQ_LEN, CQT_BINS)
    session = _get_session()
    out = []
    for g in range(0, n_win, BATCH_WINDOWS):
        batch = np.zeros((BATCH_WINDOWS, SEQ_LEN, CQT_BINS), np.float32)
        n = min(BATCH_WINDOWS, n_win - g)
        batch[:n] = x[g:g + n]
        out.append(session.run(None, {"features": batch})[0][:n])
    logits = np.concatenate(out).reshape(-1, len(VOCAB))[:t]
    k = SMOOTH_FRAMES
    padded = np.pad(logits, ((k // 2, k // 2), (0, 0)), mode="edge")
    csum = np.cumsum(np.vstack([np.zeros((1, logits.shape[1])), padded]), axis=0)
    return ((csum[k:] - csum[:-k]) / k).astype(np.float32)


def load_mono_22k(paths) -> tuple[np.ndarray, float]:
    """Suma de los archivos, mono como media aritmética (L+R)/2 —el modelo
    es sensible a la ganancia y se entrenó así— y remuestreada a 22050 Hz.
    Devuelve también la duración en segundos."""
    import soundfile as sf
    mix, sr = None, None
    for p in paths:
        data, file_sr = sf.read(str(p), dtype="float32", always_2d=True)
        if sr is not None and file_sr != sr:
            raise ValueError(f"tasas distintas entre stems: {file_sr} vs {sr}")
        sr = file_sr
        mono = data.mean(axis=1)
        if mix is None:
            mix = mono
        else:
            n = min(len(mix), len(mono))
            mix = mix[:n] + mono[:n]
    if mix is None or not len(mix):
        raise ValueError("sin audio")
    duration = len(mix) / sr
    if sr != CQT_SR:
        g = np.gcd(int(sr), CQT_SR)
        mix = _resample(mix, CQT_SR // g, int(sr) // g)
    return mix, duration


def detect_chords(folder) -> dict:
    """Analiza los stems de `folder/separated/` y devuelve los datos para
    `write_chords` (no escribe). Lanza si faltan stems o el motor."""
    folder = Path(folder)
    paths = [folder / "separated" / f"{s}.mp3" for s in SOURCE_STEMS]
    y, duration = load_mono_22k(paths)
    probs = run_model(cqt_features(y))
    # Confianza = probabilidad softmax del ganador sobre los logits suavizados
    e = np.exp(probs - probs.max(axis=1, keepdims=True))
    conf = 1.0 / e.sum(axis=1)
    frames = [(VOCAB[i], float(c)) for i, c in zip(probs.argmax(axis=1), conf)]
    data = postprocess(frames, FRAME_S, duration)
    data.update(engine=ENGINE_NAME, source=list(SOURCE_STEMS))
    return data


def ensure_chords(folder, force: bool = False) -> bool:
    """Detecta y escribe `chords.json` si falta (o siempre con `force`).

    Sin `force` nunca pisa un archivo existente: puede tener correcciones a
    mano. Devuelve True si escribió.
    """
    folder = Path(folder)
    if not force and (folder / CHORDS_FILE).exists():
        return False
    write_chords(folder, detect_chords(folder))
    return True


class ChordsQueue:
    """Un solo hilo de fondo para las canciones separadas antes de que
    existiera la detección (o cuyo análisis se pide de nuevo). Misma forma
    que `LyricsFetchQueue`: daemon vivo todo el proceso, bloqueado en `get()`.

    `on_done(folder: str, ok: bool)` se llama desde ESTE hilo: quien toque
    widgets debe pasar por una señal Qt.

    Sin `force`, una carpeta se intenta una sola vez por sesión: una canción
    sin stems (o con stems ilegibles) no se reintenta en cada reproducción.
    """

    def __init__(self, on_done):
        self._on_done = on_done
        self._queue: queue.Queue = queue.Queue()
        self._tried: set[str] = set()
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, folder, force: bool = False):
        key = str(folder)
        if not force and key in self._tried:
            return
        self._tried.add(key)
        self._queue.put((key, force))

    def _run(self):
        while True:
            folder, force = self._queue.get()
            ok = False
            try:
                ok = ensure_chords(folder, force=force)
            except Exception as e:
                logger.error("No se pudieron detectar acordes en %s: %s", folder, e)
            finally:
                self._queue.task_done()
            try:
                self._on_done(folder, ok)
            except Exception:
                pass  # el receptor pudo morir al cerrar la app
