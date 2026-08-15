<div align="center">

<img src="images/main_window/main_icon.png" width="120" alt="PlayIt">

# PlayIt

**Reproductor de audio con separación de pistas integrada · Audio player with built-in stem separation**

[![Versión](https://img.shields.io/badge/versión-2.0-blueviolet)](https://github.com/RavilesX/playit/releases/latest)
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
- **Modo remoto**: controlá la reproducción desde el teléfono con [PlayIt Mobile](https://github.com/RavilesX/playit_mobile) por Wi-Fi (emparejamiento por QR, sin salir de la red local).
- **Playlists** `.mlst` con ordenamiento por artista/título y modo aleatorio.
- **Información del archivo original**: metadata (artista, álbum, año, género, formato, kbps) guardada al separar y consultable desde la playlist.
- **Instalador de dependencias integrado**: la app detecta e instala lo que falta desde su propio menú.

### Modo remoto (PlayIt Mobile)

Para el músico que ensaya lejos de la PC: el teléfono controla la reproducción del escritorio por Wi-Fi.

1. En el escritorio: **Opciones → Modo remoto (PlayIt Mobile)…**
2. En [PlayIt Mobile](https://github.com/RavilesX/playit_mobile): escaneá el QR que aparece (o escribí a mano la dirección y el código).
3. Desde el teléfono: play/pausa, detener, anterior, siguiente, repetir y elegir cualquier canción de la lista.

Detalles que conviene saber:

- **El audio nunca sale de la PC.** Por la red viajan la lista de canciones (texto), las carátulas y comandos de pocos bytes.
- **Sólo red local.** Ambos equipos tienen que estar en la misma Wi-Fi; el servidor rechaza conexiones que no vengan de una dirección privada. No funciona con datos móviles ni fuera de la red, y las redes de invitados con aislamiento de clientes lo bloquean.
- **El código se conserva entre reinicios**, así el teléfono se reconecta solo; si el router le cambia la IP a la PC, la vuelve a encontrar sola. **"Generar nuevo código"** desempareja cualquier teléfono anterior.
- **Sin cifrado**: el código viaja en claro por la red local. En una red doméstica o de sala de ensayo es aceptable —lo peor que puede pasar es que alguien te cambie la canción—; en una red pública, conviene generar un código nuevo al terminar.
- Windows puede pedir permiso de firewall dos veces (TCP y UDP): hay que permitirlo en **redes privadas**.

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

`portaudio19-dev` y `libsndfile1` son el backend de audio de `sounddevice`/`soundfile`; en Windows y macOS los wheels de pip ya los incluyen. `qrcode` es opcional: sin él, el modo remoto se empareja escribiendo la dirección y el código a mano.

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

**v2.0** — **modo remoto**: PlayIt Mobile controla la reproducción del escritorio por Wi-Fi (play/pausa, detener, anterior/siguiente, repetir y elegir canción de la lista). Se activa desde **Opciones → Modo remoto**, que abre un diálogo con un **QR de emparejamiento** —más la dirección y el código para tipear a mano si el teléfono no puede escanear— y muestra **"Remoto: activo"** en la barra de estado. El servidor sólo acepta conexiones de la red local y exige el código en cada petición; **el audio nunca sale de la PC**. El teléfono ve la lista completa con artista, título y duración, y las **carátulas** de cada canción; el **código se conserva entre reinicios** y la app se **redescubre sola en la red** si el router le cambia la IP al escritorio, así que el emparejamiento se hace una sola vez ("Generar nuevo código" lo revoca). Historial completo en [Releases](https://github.com/RavilesX/playit/releases).

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
- **Remote mode**: control playback from your phone with [PlayIt Mobile](https://github.com/RavilesX/playit_mobile) over Wi-Fi (QR pairing, never leaves the local network).
- **`.mlst` playlists** with artist/title sorting and a random mode.
- **Source file info**: metadata (artist, album, year, genre, format, kbps) saved at split time and viewable from the playlist.
- **Built-in dependency installer**: the app detects and installs what's missing from its own menu.

### Remote mode (PlayIt Mobile)

For the musician rehearsing away from the computer: the phone drives desktop playback over Wi-Fi.

1. On the desktop: **Opciones → Modo remoto (PlayIt Mobile)…**
2. In [PlayIt Mobile](https://github.com/RavilesX/playit_mobile): scan the QR code shown (or type the address and code by hand).
3. From the phone: play/pause, stop, previous, next, repeat, and pick any song in the list.

Worth knowing:

- **Audio never leaves the PC.** Only the track list (text), cover art and a few bytes of commands travel over the network.
- **Local network only.** Both devices must be on the same Wi-Fi; the server rejects connections from non-private addresses. It won't work over mobile data or outside the network, and guest networks with client isolation block it.
- **The code survives restarts**, so the phone reconnects on its own; if the router changes the PC's IP, it finds it again by itself. **"Generar nuevo código"** unpairs any previously paired phone.
- **No encryption**: the code travels in the clear over the local network. Fine at home or in a rehearsal room —worst case someone skips your song—; on a public network, generate a new code when you're done.
- Windows may ask for firewall permission twice (TCP and UDP); allow it on **private networks**.

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

`portaudio19-dev` and `libsndfile1` are the audio backend for `sounddevice`/`soundfile`; on Windows and macOS the pip wheels already bundle them. `qrcode` is optional: without it, remote mode is paired by typing the address and code by hand.

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

**v2.0** — **remote mode**: PlayIt Mobile drives desktop playback over Wi-Fi (play/pause, stop, previous/next, repeat, and picking any song from the list). Turn it on from **Opciones → Modo remoto**, which opens a dialog with a **pairing QR code** —plus the address and code to type by hand if the phone can't scan— and shows **"Remoto: activo"** in the status bar. The server only accepts local-network connections and requires the code on every request; **audio never leaves the PC**. The phone gets the full list with artist, title and duration, plus each song's **cover art**; the **code survives restarts** and the app **finds the desktop again on the network** if the router changes its IP, so pairing happens once ("Generar nuevo código" revokes it). Full history in [Releases](https://github.com/RavilesX/playit/releases).

## Contact

- **Author**: Ricardo Aviles Sanders (RavilesX)
- **Email**: ravilesx@gmail.com
- **GitHub**: [github.com/RavilesX](https://github.com/RavilesX)

Bug reports and suggestions: [Issues](https://github.com/RavilesX/playit/issues).

## License

[GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html) © 2025-2026 Ricardo Aviles Sanders
