# playit
Reproductor de audio con demucs integrado
Versión funcional en Windows y Linux
Probado en:

Windows 10

Windows 11

Linux Mint

Linux Ubuntu

Linux Suse

Para ejecutarlo en Linux desde la consola:

1.- Instala las dependencias del sistema

sudo apt update

sudo apt install python3 python3-pip python3-venv ffmpeg portaudio19-dev libsndfile1

portaudio19-dev es necesario porque sounddevice lo usa por debajo para hablar con el hardware de audio, en Windows esto viene incluido, pero en Linux hay que instalarlo explícitamente. libsndfile1 es lo mismo pero para soundfile.

2.- Crea un entorno virtual y activa

python3 -m venv venv

source venv/bin/activate

3.- Instala las dependencias Python

pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics

sudo apt install libxcb-cursor0

4.- Ejecuta

python3 main.py

Para no escribir todo eso cada vez, puedes crear un script de arranque:

bash#!/bin/bash

cd ~/playit

source venv/bin/activate

python3 main.py

Guárdalo como playit.sh, dale permisos con chmod +x playit.sh, y ya solo ejecutas ./playit.sh.


Cualquier duda o colaboración

ravilesx@gmail.com

## Análisis del Código

### Arquitectura General
PlayIt es un reproductor de audio avanzado con separación de fuentes integrada utilizando Demucs. La aplicación está construida con PyQt6 para la interfaz gráfica y utiliza un sistema de workers en hilos separados para tareas pesadas como descarga, separación de audio e instalación de dependencias.

### Componentes Principales

#### Núcleo de la Aplicación
- **main.py**: Punto de entrada principal. Crea la aplicación PyQt6, muestra una pantalla de splash y inicializa el AudioPlayer.
- **audio_player.py**: Clase principal que maneja la interfaz de usuario y la lógica del reproductor. Incluye gestión de playlists, controles de reproducción, visualización de letras y separación de audio.

#### Workers de Procesamiento
- **demucs_worker.py**: Maneja la separación de audio en stems (drums, vocals, bass, other) usando el modelo htdemucs_ft de Demucs.
- **ytdlp_worker.py**: Procesa archivos de audio descargados con yt-dlp, convirtiéndolos a formato WAV para separación.
- **ffmpeg_worker.py**: Utiliza FFmpeg para conversión de formatos de audio.
- **ytdlp_download_worker.py**: Descarga audio desde YouTube u otras plataformas usando yt-dlp.

#### Workers de Instalación
- **demucs_install_worker.py**: Instala Demucs y sus dependencias (PyTorch, etc.).
- **cuda_worker.py**: Instala soporte CUDA para aceleración GPU.
- **python_worker.py**: Instala Python si no está disponible.
- **visualc_worker.py**: Instala Visual C++ Redistributables en Windows.
- **ffmpeg_worker.py**: Instala FFmpeg.

#### Utilidades y UI
- **platform_utils.py**: Funciones específicas de plataforma (Windows/Linux) para ejecutar comandos, detectar GPU, etc.
- **resources.py**: Gestión de recursos (imágenes, mensajes estilizados).
- **lazy_resources.py**: Carga diferida de recursos pesados (audio, imágenes, letras, playlists).
- **ui_components.py**: Componentes personalizados de UI (barras de título, diales, grips de tamaño).
- **dialogs.py**: Diálogos modales (acerca de, cola, separación, descarga).
- **base_worker.py**: Clase base para workers con señales PyQt6.

### Características Principales
- **Reproducción de Audio**: Soporte para múltiples formatos con sounddevice/soundfile.
- **Separación de Fuentes**: Integración con Demucs para separar pistas en componentes individuales.
- **Descarga desde YouTube**: Descarga de audio desde plataformas de video.
- **Gestión de Playlists**: Carga y gestión de bibliotecas musicales.
- **Visualización de Letras**: Búsqueda y display de letras de canciones.
- **Interfaz Personalizable**: Tema oscuro con imágenes de fondo y estilos CSS.
- **Instalación Automática**: Detección e instalación automática de dependencias faltantes.

### Tecnologías Utilizadas
- **PyQt6**: Framework para interfaz gráfica.
- **Demucs**: Biblioteca para separación de fuentes de audio.
- **yt-dlp**: Herramienta para descarga de video/audio.
- **FFmpeg**: Procesamiento de multimedia.
- **Sounddevice/Soundfile**: Reproducción y manipulación de audio.
- **Requests**: Para búsquedas de letras y metadatos.
- **Mutagen/Pillow**: Manejo de metadatos y imágenes.

### Estructura de Archivos
```
├── main.py                 # Punto de entrada
├── audio_player.py         # Interfaz principal
├── dialogs.py              # Diálogos de UI
├── ui_components.py        # Componentes UI personalizados
├── resources.py            # Gestión de recursos
├── lazy_resources.py       # Carga diferida
├── platform_utils.py       # Utilidades de plataforma
├── base_worker.py          # Clase base para workers
├── *_worker.py             # Workers especializados
├── estilos.css             # Estilos de la aplicación
├── images/                 # Recursos gráficos
└── README.md               # Este archivo
```
