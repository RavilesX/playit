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
pip install PyQt6 sounddevice soundfile numpy requests mutagen Pillow psutil
sudo apt install libxcb-cursor0

5.- Ejecuta
python3 main.py

Para no escribir todo eso cada vez, puedes crear un script de arranque:
bash#!/bin/bash
cd ~/playit
source venv/bin/activate
python3 main.py

Guárdalo como playit.sh, dale permisos con chmod +x playit.sh, y ya solo ejecutas ./playit.sh.


Cualquier duda o colaboración
ravilesx@gmail.com
