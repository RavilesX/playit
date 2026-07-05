# Migración a Python arm64 nativo en el Mac Mini M2 (aceleración MPS para Demucs)

> Contexto para una sesión futura de Claude Code corriendo en el Mac Mini.
> Objetivo: que la separación de pistas con Demucs use la GPU (MPS) del M2
> en vez del fallback a CPU. Ganancia estimada: ~12 min → ~3-6 min por canción.

## Estado actual (2026-07-04)

- Mac Mini M2 (arm64), macOS. Usuario: `ricardoaviles`.
- La app (rama `macos-support`) funciona: reproduce, separa canciones (CPU) y descarga.
- **Anaconda instalado en `~/anaconda3` es build Intel (x86_64), corre bajo Rosetta.**
  Verificado: `pip install torch==2.5.1` falla porque PyTorch dejó de publicar
  wheels x86_64 para macOS después de 2.2.2 (solo ofrece hasta 2.2.2).
- Ese Anaconda provee el `python3` que la app usa hoy; demucs está instalado ahí
  con un torch viejo (~2.0/2.1, Python 3.10).
- El intento MPS falla con:
  `TypeError: Trying to convert ComplexFloat to the MPS backend but it does not have support for that dtype.`
  htdemucs necesita FFT/números complejos en MPS, soportados a partir de torch ~2.4-2.5.
  Con torch x86 ≤2.2.2 es callejón sin salida — no basta con actualizar dentro de Anaconda.
- La app ya tiene fallback automático MPS→CPU (`demucs_worker.py`), así que nada
  de esto rompe la funcionalidad: si MPS falla, separa en CPU.
- Log de fallos de separación: `~/Music/PlayIt/demucs_error.log`.

## Cómo la app elige Python (relevante para la integración)

- `platform_utils.get_python_cmd()` retorna `python3` resuelto contra el PATH
  del proceso de la app.
- En macOS, `run_silent()` inyecta `/opt/homebrew/bin` y `/usr/local/bin` al
  PATH de los subprocesos, pero los **agrega al final** (`_augment_mac_path`).
  Hoy el python3 de Anaconda gana. Tras la migración habrá que verificar qué
  python3 resuelve la app lanzada desde Finder (no hereda el PATH del shell).
- Detección MPS: `platform_utils.check_pytorch_mps()` ejecuta
  `python3 -c "import torch; torch.backends.mps.is_available()"`.

## Plan (opción B)

1. **Diagnóstico previo** (confirmar estado antes de tocar nada):
   ```bash
   uname -m                                    # arm64 (hardware)
   which -a python3
   python3 -c "import platform; print(platform.machine())"   # x86_64 = Rosetta
   python3 -c "import torch; print(torch.__version__)"
   ```

2. **Instalar Python arm64 nativo.** Opciones, en orden de preferencia:
   - **Miniforge** (conda-forge, nativo arm64): `brew install miniforge`.
     Crear env dedicado: `conda create -n playit python=3.12 && conda activate playit`.
   - O `brew install python@3.12` (ojo: es "externally managed", PEP 668 —
     usar venv o `--break-system-packages`).

3. **Instalar el stack en el entorno nuevo:**
   ```bash
   pip install "torch==2.5.1" "torchaudio==2.5.1" demucs
   ```
   **Fijar torch 2.5.1 — NO la última**: torch ≥2.6 cambió el default de
   `weights_only` en `torch.load` y demucs 4.0.1 truena cargando sus modelos.
   Verificar arm64 + MPS:
   ```bash
   python3 -c "import platform, torch; print(platform.machine(), torch.__version__, torch.backends.mps.is_available())"
   ```

4. **Prueba manual de separación con MPS** antes de tocar la app:
   ```bash
   PYTORCH_ENABLE_MPS_FALLBACK=1 python3 -m demucs -n htdemucs_ft -d mps --mp3 -o /tmp/sep "algún.mp3"
   ```
   Debe terminar sin traceback y en una fracción del tiempo de CPU.
   (Los modelos ya están cacheados en `~/.cache/torch/hub/checkpoints/`.)

5. **Hacer que la app use ese Python.** El punto delicado. Alternativas:
   - Que el python3 arm64 quede primero en el PATH que ve la app (recordar:
     Finder no lee `.zshrc`; revisar cómo está resolviendo hoy el de Anaconda).
   - O mejorar `get_python_cmd()` en `platform_utils.py`: en macOS, preferir
     candidatos nativos (p. ej. `/opt/homebrew/bin/python3`, el env de
     miniforge) probando `platform.machine() == 'arm64'` y que tenga demucs.
   - Posible cambio complementario: que `_augment_mac_path` haga *prepend* en
     vez de append — evaluar impacto antes (hoy el orden actual es lo que hace
     funcionar el setup con Anaconda).

6. **Prueba end-to-end desde la app** (menú Dividir) y revisar que ya no
   aparezca "Intento con MPS falló" en `~/Music/PlayIt/demucs_error.log`.

## Precauciones

- **No desinstalar Anaconda ni cambiar su prioridad de PATH global** sin
  inventariar qué más depende de él en esa máquina.
- Mantener el fallback MPS→CPU intacto: es la red de seguridad.
- Si algo se rompe, el estado funcional conocido es: Anaconda x86 + demucs +
  separación en CPU (~12 min/canción con htdemucs_ft).
