#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Genera el ejecutable de Windows (dist/PlayIt.exe) desde Linux usando Docker.
#
# PyInstaller no puede cross-compilar: un .exe de Windows necesita Python de
# Windows. La imagen batonogov/pyinstaller-windows trae Wine + Python de
# Windows + PyInstaller preinstalados, así que todo el build ocurre dentro
# del contenedor con el mismo PlayIt.spec de siempre.
#
# Requisitos: Docker instalado y usable sin sudo (grupo docker).
# Uso:        ./build_windows.sh
# Salida:     dist/PlayIt.exe
#
# Notas:
# - La primera ejecución descarga la imagen (~1 GB) y los paquetes pip;
#   las siguientes usan caché y tardan unos minutos.
# - Demucs/PyTorch NO se empaquetan: la app los ejecuta como subproceso
#   del Python del sistema del usuario (igual que yt-dlp y ffmpeg).
# - Si se agrega una dependencia Python al proyecto, agregarla también
#   a la lista de pip install de abajo.
# - El warning "could not resolve 'icuuc.dll'" es benigno (PyQt6 no la usa).
# - Probar el exe en Windows real antes de distribuir: Wine compila bien
#   pero no sustituye una prueba de ejecución.
# - El binario de Linux se genera aparte, sin Docker: pyinstaller PlayIt.spec
# ──────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

docker run --rm -v "$PWD:/src" batonogov/pyinstaller-windows:latest \
  "pip install --no-warn-script-location PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil syncedlyrics && \
   pyinstaller --clean -y --dist ./dist --workpath /tmp PlayIt.spec && \
   chown -R --reference=. ./dist"

echo
echo "Listo: $(ls -lh dist/PlayIt.exe | awk '{print $5, $9}')"
