<div align="center">

<img src="images/main_window/main_icon.png" width="120" alt="PlayIt">

# PlayIt

**Reproductor de audio con separación de pistas integrada · Audio player with built-in stem separation**

[![Versión](https://img.shields.io/badge/versión-1.2.7-blueviolet)](https://github.com/RavilesX/playit/releases/latest)
[![Licencia](https://img.shields.io/badge/licencia-GPL--3.0-blue)](LICENSE)
[![Plataformas](https://img.shields.io/badge/plataformas-Windows%20%7C%20Linux%20%7C%20macOS-informational)](#sistemas-soportados)

[Español](#español) · [English](#english)

</div>

---

# Español

## Descripción

PlayIt es un reproductor de audio de escritorio que separa canciones en cuatro pistas independientes (batería, voz, bajo y otros instrumentos) usando [Demucs](https://github.com/facebookresearch/demucs), y las reproduce de forma simultánea con volumen y silencio independientes por pista. Ideal para practicar un instrumento, hacer karaoke o estudiar mezclas.

### Características

- **Separación de pistas** con Demucs (modelo `htdemucs_ft`), con aceleración GPU (CUDA en NVIDIA, MPS en Apple Silicon) y cola de procesamiento. Acepta entrada en mp3, wav, flac, ogg, opus, m4a, aac, aiff, wma y wv; la salida siempre es mp3.
- **Reproducción multi-pista**: 4 stems sincronizados con control de volumen/mute individual.
- **Letras sincronizadas (LRC)**: descarga automática, offset ajustable, colores por intérprete y editor visual de sincronización sobre la forma de onda de la voz.
- **Auto-unmute**: reactiva la voz con fundido en las secciones sin letra (modo karaoke inteligente).
- **Descarga desde YouTube** (yt-dlp) directa a MP3.
- **Visualizador de audio** tipo CAVA renderizado en NumPy.
- **Playlists** `.mlst` con ordenamiento por artista/título y modo aleatorio.
- **Información del archivo original**: metadata (artista, álbum, año, género, formato, kbps) guardada al separar y consultable desde la playlist.
- **Instalador de dependencias integrado**: la app detecta e instala lo que falta desde su propio menú.

## Sistemas soportados

| Sistema | Estado |
|---|---|
| Windows 10 / 11 | ✅ Probado |
| Linux (Mint, Ubuntu, openSUSE) | ✅ Probado |
| macOS (Apple Silicon) | ✅ Probado en Mac Mini M2 |
| macOS (Intel) | ⚠️ Sin binario oficial; posible desde código fuente |

## Requisitos de hardware

|  | Mínimo | Recomendado |
|---|---|---|
| CPU | Doble núcleo 64 bits | 4+ núcleos |
| RAM | 4 GB (solo reproducción) / 8 GB (separación) | 16 GB |
| GPU | No requerida | NVIDIA con CUDA, o Apple Silicon (MPS) |
| Disco | ~1 GB (app + modelos) | 3 GB+ (biblioteca separada crece ~40 MB por canción) |

Tiempos de referencia separando una canción de ~4:30 con `htdemucs_ft`:

- Apple M2 (MPS): **~3 min**
- CPU moderna sin GPU: **~12 min**

## Instalación (ejecutables)

Descarga la última versión desde [Releases](https://github.com/RavilesX/playit/releases/latest).

**Windows** — descarga `PlayIt-vX.Y.Z-windows.exe` y ejecútalo.

**Linux** — descarga `PlayIt-vX.Y.Z-linux.tar.gz`:

```bash
tar -xzf PlayIt-vX.Y.Z-linux.tar.gz
./PlayIt
```

**macOS** — descarga `PlayIt-vX.Y.Z-macos.zip`, descomprime y, como la app no está firmada, autorízala la primera vez:

```bash
xattr -cr PlayIt.app
open PlayIt.app
```

(o clic derecho sobre `PlayIt.app` → Abrir → Abrir).

#### Crear y anclar un lanzador al panel (Linux Mint)

1. Crea un archivo `PlayIt.desktop` en el escritorio con este contenido:

```ini
[Desktop Entry]
Version=1.0
Name=PlayIt
Comment=Reproductor de Audio con Demucs Integrado
Exec=/ruta/completa/hacia/PlayIt
Path=/ruta/completa/hacia/la/carpeta/donde/esta/PlayIt
Icon=/ruta/completa/hacia/el/main_icon.png
Type=Application
Terminal=false
StartupWMClass=PlayIt
```

2. Ejecuta:

```bash
mv ~/Escritorio/PlayIt.desktop ~/.local/share/applications/
```

3. Abre PlayIt desde el menú principal de Linux.
4. Clic derecho sobre el icono en el panel de tareas → "Añadir/Agregar/Anclar al panel".

### Dependencias externas

La app las detecta y ofrece instalarlas desde **Opciones → Dependencias**:

| Dependencia | Para qué | Notas |
|---|---|---|
| Python 3.10+ | Demucs y yt-dlp | |
| FFmpeg | Decodificar/convertir audio | |
| Demucs (+ PyTorch) | Separación de pistas | En Apple Silicon se instala en un entorno nativo con MPS automáticamente |
| yt-dlp | Descarga desde YouTube | Opcional |
| CUDA (PyTorch) | Aceleración NVIDIA | Opcional; requiere GPU NVIDIA |
| Visual C++ Redistributable | Solo Windows | |

En macOS el instalador integrado requiere [Homebrew](https://brew.sh).

## Ejecución desde código fuente

**Linux**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv ffmpeg portaudio19-dev libsndfile1 libxcb-cursor0
git clone https://github.com/RavilesX/playit.git && cd playit
python3 -m venv venv && source venv/bin/activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python3 main.py
```

`portaudio19-dev` y `libsndfile1` son el backend de audio de `sounddevice`/`soundfile`; en Windows y macOS los wheels de pip ya los incluyen.

**macOS**

```bash
brew install ffmpeg
git clone https://github.com/RavilesX/playit.git && cd playit
python3 -m venv venv && source venv/bin/activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python3 main.py
```

**Windows** (con [Python 3.10+](https://www.python.org/downloads/) y [FFmpeg](https://ffmpeg.org) instalados)

```powershell
git clone https://github.com/RavilesX/playit.git; cd playit
python -m venv venv; .\venv\Scripts\activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python main.py
```

### Tests y build

```bash
pip install pytest pytest-qt pyinstaller
pytest                      # suite de pruebas (headless)
pyinstaller PlayIt.spec     # genera el ejecutable (PlayIt.app en macOS)
```

## Versión actual

**v1.2.7** — soporte de entrada para más formatos de audio (wav, flac, ogg, opus, m4a, aac, aiff, wma, wv…), con extracción de portada por formato; opción **"Información"** en el menú contextual de la playlist, que muestra la metadata del archivo usado al separar (artista, canción, álbum, año, género, formato y kbps) guardada ahora en el `data.json` —las canciones separadas antes aparecen como "Desconocido"—; orden **aleatorio** de la playlist (botón y menú); en el editor de sincronización: **formato automático** del texto (mayúscula inicial por renglón, desactivable), atajo **Ctrl+A** para unir líneas y nueva distribución de la barra de herramientas; y fuentes tipográficas empaquetadas con la app (Saira Stencil One, Righteous, Space Mono y Rubik Doodle Triangles, con sus licencias OFL). Historial completo en [Releases](https://github.com/RavilesX/playit/releases).

## Contacto

- **Autor**: Ricardo Aviles Sanders (RavilesX)
- **Email**: ravilesx@gmail.com
- **GitHub**: [github.com/RavilesX](https://github.com/RavilesX)

Reportes de bugs y sugerencias: [Issues](https://github.com/RavilesX/playit/issues).

## Licencia

[GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html) © 2025-2026 Ricardo Aviles Sanders

---

# English

## Overview

PlayIt is a desktop audio player that splits songs into four independent stems (drums, vocals, bass and other instruments) using [Demucs](https://github.com/facebookresearch/demucs), and plays them back simultaneously with per-stem volume and mute. Great for practicing an instrument, karaoke, or studying mixes.

### Features

- **Stem separation** with Demucs (`htdemucs_ft` model), GPU-accelerated (CUDA on NVIDIA, MPS on Apple Silicon), with a processing queue. Input can be mp3, wav, flac, ogg, opus, m4a, aac, aiff, wma or wv; output is always mp3.
- **Multi-stem playback**: 4 synchronized stems with individual volume/mute.
- **Synced lyrics (LRC)**: automatic fetching, adjustable offset, per-singer colors, and a visual sync editor over the vocals waveform.
- **Auto-unmute**: fades vocals back in during sections without lyrics (smart karaoke mode).
- **YouTube download** (yt-dlp) straight to MP3.
- **CAVA-style audio visualizer** rendered in NumPy.
- **`.mlst` playlists** with artist/title sorting and a random mode.
- **Source file info**: metadata (artist, album, year, genre, format, kbps) saved at split time and viewable from the playlist.
- **Built-in dependency installer**: the app detects and installs what's missing from its own menu.

## Supported systems

| System | Status |
|---|---|
| Windows 10 / 11 | ✅ Tested |
| Linux (Mint, Ubuntu, openSUSE) | ✅ Tested |
| macOS (Apple Silicon) | ✅ Tested on a Mac Mini M2 |
| macOS (Intel) | ⚠️ No official binary; possible from source |

## Hardware requirements

|  | Minimum | Recommended |
|---|---|---|
| CPU | 64-bit dual core | 4+ cores |
| RAM | 4 GB (playback only) / 8 GB (separation) | 16 GB |
| GPU | Not required | NVIDIA with CUDA, or Apple Silicon (MPS) |
| Disk | ~1 GB (app + models) | 3 GB+ (separated library grows ~40 MB per song) |

Reference times separating a ~4:30 song with `htdemucs_ft`:

- Apple M2 (MPS): **~3 min**
- Modern CPU, no GPU: **~12 min**

## Installation (binaries)

Download the latest version from [Releases](https://github.com/RavilesX/playit/releases/latest).

**Windows** — download `PlayIt-vX.Y.Z-windows.exe` and run it.

**Linux** — download `PlayIt-vX.Y.Z-linux.tar.gz`:

```bash
tar -xzf PlayIt-vX.Y.Z-linux.tar.gz
./PlayIt
```

**macOS** — download `PlayIt-vX.Y.Z-macos.zip`, unzip it and, since the app is unsigned, authorize it on first launch:

```bash
xattr -cr PlayIt.app
open PlayIt.app
```

(or right-click `PlayIt.app` → Open → Open).

#### Create and pin a launcher to the panel (Linux Mint)

1. Create a `PlayIt.desktop` file on the desktop with this content:

```ini
[Desktop Entry]
Version=1.0
Name=PlayIt
Comment=Audio Player with Integrated Demucs
Exec=/full/path/to/PlayIt
Path=/full/path/to/the/folder/containing/PlayIt
Icon=/full/path/to/main_icon.png
Type=Application
Terminal=false
StartupWMClass=PlayIt
```

2. Run:

```bash
mv ~/Desktop/PlayIt.desktop ~/.local/share/applications/
```

3. Open PlayIt from the Linux main menu.
4. Right-click the icon in the taskbar panel → "Add/Pin to panel".

### External dependencies

The app detects them and offers to install them from **Opciones → Dependencias**:

| Dependency | Purpose | Notes |
|---|---|---|
| Python 3.10+ | Demucs and yt-dlp | |
| FFmpeg | Audio decoding/conversion | |
| Demucs (+ PyTorch) | Stem separation | On Apple Silicon it installs into a native venv with MPS automatically |
| yt-dlp | YouTube download | Optional |
| CUDA (PyTorch) | NVIDIA acceleration | Optional; requires an NVIDIA GPU |
| Visual C++ Redistributable | Windows only | |

On macOS the built-in installer requires [Homebrew](https://brew.sh).

## Running from source

**Linux**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv ffmpeg portaudio19-dev libsndfile1 libxcb-cursor0
git clone https://github.com/RavilesX/playit.git && cd playit
python3 -m venv venv && source venv/bin/activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python3 main.py
```

`portaudio19-dev` and `libsndfile1` are the audio backend for `sounddevice`/`soundfile`; on Windows and macOS the pip wheels already bundle them.

**macOS**

```bash
brew install ffmpeg
git clone https://github.com/RavilesX/playit.git && cd playit
python3 -m venv venv && source venv/bin/activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python3 main.py
```

**Windows** (with [Python 3.10+](https://www.python.org/downloads/) and [FFmpeg](https://ffmpeg.org) installed)

```powershell
git clone https://github.com/RavilesX/playit.git; cd playit
python -m venv venv; .\venv\Scripts\activate
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics qrcode
python main.py
```

### Tests and build

```bash
pip install pytest pytest-qt pyinstaller
pytest                      # test suite (headless)
pyinstaller PlayIt.spec     # builds the executable (PlayIt.app on macOS)
```

## Current version

**v1.2.7** — input support for more audio formats (wav, flac, ogg, opus, m4a, aac, aiff, wma, wv…), with per-format cover art extraction; an **"Información"** entry in the playlist context menu showing the metadata of the file used for separation (artist, title, album, year, genre, format and kbps), now stored in `data.json` —songs separated earlier show as "Desconocido"—; **random** playlist ordering (button and menu); in the sync editor: **automatic text formatting** (sentence case per line, can be turned off), **Ctrl+A** to merge lines and a reworked toolbar layout; and typefaces bundled with the app (Saira Stencil One, Righteous, Space Mono and Rubik Doodle Triangles, with their OFL licenses). Full history in [Releases](https://github.com/RavilesX/playit/releases).

## Contact

- **Author**: Ricardo Aviles Sanders (RavilesX)
- **Email**: ravilesx@gmail.com
- **GitHub**: [github.com/RavilesX](https://github.com/RavilesX)

Bug reports and suggestions: [Issues](https://github.com/RavilesX/playit/issues).

## License

[GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html) © 2025-2026 Ricardo Aviles Sanders
