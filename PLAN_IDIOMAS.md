# Plan: selector de idioma (Español / Português / English)

Estado: análisis, sin código. Fecha: 2026-10-05.

## 1. Diagnóstico actual

- **Todo el texto de UI está hardcodeado en español** dentro de los `.py`. No existe
  `tr()`, ni `QTranslator`, ni archivos de traducción.
- **No existe ningún archivo de preferencias**: la app no guarda nada entre sesiones salvo
  `remote_token.json` en `get_data_dir()`. Hay que crear la persistencia desde cero.
- Volumen aproximado de cadenas visibles (heurística AST, incluye algo de ruido):

  | Archivo | Cadenas aprox. |
  |---|---|
  | `audio_player.py` | ~140 |
  | `dialogs.py` | ~85 |
  | `lyrics_sync_editor.py` | ~85 |
  | `dependencies.py` | ~40 |
  | `lazy_resources.py`, `demucs_worker.py`, `ytdlp_download_worker.py`, `demucs_queue.py` | ~70 entre todos |
  | resto (workers, `platform_utils`, `ui_components`, `resources`) | ~40 |

  Estimado real tras depurar: **~350-400 cadenas**, ~30-40 de ellas f-strings con variables.
- ~65 llamadas a `QMessageBox.*`: sus botones estándar (Yes/No/OK/Cancel) los pinta Qt, igual
  que `QInputDialog` y `QFileDialog` no nativo. Hoy salen en el idioma del sistema o en inglés.
- **Imágenes con texto horneado**: solo `images/split_dialog/extract_name_btn.png`
  ("Autollenado"). `aceptar_btn.png` (OK) y `cancelar_btn.png` (X) son neutros.

## 2. Decisiones de diseño (recomendadas)

### 2.1 Mecanismo: `tr()` propio + JSON, con el español como clave

Un módulo nuevo `i18n.py` con:
- `tr(texto_es: str) -> str`: busca la traducción del idioma activo; si no hay, devuelve el
  español (fallback automático, nunca rompe).
- Diccionarios en `locales/en.json` y `locales/pt.json`: `{"Texto en español": "Translation"}`.
  El español no necesita archivo: es la clave.

Por qué no las alternativas:
- **Qt Linguist (`self.tr()` + `.ts`/`.qm`)**: necesita `lrelease`, que no viene en el wheel de
  PyQt6 (habría que instalar Qt tools aparte en cada máquina de build y en CI). Además `self.tr()`
  requiere contexto de clase, incómodo para constantes de módulo y workers.
- **gettext (`.po`/`.mo`)**: stdlib, pero exige compilar `.mo` (paso extra en build y CI).
- **JSON**: cero dependencias, cero compilación, PyInstaller solo empaqueta la carpeta.

Clave = texto español (estilo gettext) en vez de claves simbólicas (`"menu.file.open"`): el código
sigue leyéndose en español, y lo no traducido cae solo al español. Riesgo: si se edita el texto
español, la traducción queda huérfana → lo atrapa el test del paso 9.

### 2.2 Cambio de idioma: aplica al reiniciar

La UI se construye una sola vez en `AudioPlayer.__init__` (~3000 líneas, textos ya metidos en
widgets). Retraducir en caliente obligaría a reescribir toda la construcción como
`retranslate_ui()`. Además, fijar el idioma al arrancar hace `tr()` trivialmente thread-safe
para los workers (lectura de un dict que no cambia).

Al elegir idioma: guardar + aviso "El idioma se aplicará al reiniciar PlayIt". **Sin reinicio
automático**: mataría una separación Demucs en curso o la reproducción. Se puede agregar después
un botón "Reiniciar ahora" que solo aparezca si la cola de Demucs está vacía.

### 2.3 Persistencia: `<data_dir>/settings.json`

Mismo patrón que `remote_token.json` (portable en Windows/Linux, `~/Music/PlayIt` en macOS).
Contenido inicial: `{"language": "es"}`. Pensado para crecer (otras preferencias futuras).
Agregar `settings.json` al `.gitignore` (en desarrollo `data_dir` es el repo).

Alternativa equivalente: `QSettings` (registro en Windows, `~/.config` en Linux). Se descarta solo
por coherencia con `data_dir` y la portabilidad del ejecutable en Windows.

### 2.4 Idioma por defecto en el primer arranque

`QLocale.system()`: si es `es`/`pt`/`en`, usar ese; si no, **inglés**.
> Decisión pendiente tuya: ¿fallback inglés (mejor para usuarios de otros países) o español
> (comportamiento actual)?

## 3. Lo que NO se traduce (crítico)

Son contratos, datos o centinelas; traducirlos rompe cosas:

1. **`playback_state` (`"Activa"`/`"Pausada"`/`"Detenido"`)**: es estado interno, se compara en
   muchos sitios y es contrato literal del móvil (`/api/state`). Se queda en español; para
   mostrarlo en la barra de estado (`update_status`, ~línea 1809) se mapea a texto traducido.
2. **Protocolo remoto** (`remote_server.py`): claves JSON, valores de `state`, mensajes de
   `{"error": ...}`. El móvil tendrá su propia i18n.
3. **`LYRICS_NOT_FOUND_TEXT`** (`lyrics_api.py`): se escribe en `lyrics.lrc` y `needs_lyrics` lo
   busca para reintentar. El centinela en disco queda en español; solo se traduce lo que se
   muestra. Si no, cambiar de idioma dejaría archivos que ya no se reconocen como "no encontrado".
4. **Datos en disco**: nombres de carpeta (`music_library`, `mp3Downloads`), claves de
   `data.json` (`anio`, `genero`, `formato`...), claves de `.mlst`.
5. **Claves internas**: `LYRIC_COLORS` (`azul`/`blanco`/`rojo`) y `_SORT_MODES` (`artist`,
   `song`, `random`): se traduce solo la etiqueta visible.
6. **Logs** (`logger.*`, ~34 llamadas) y `demucs_error.log`: quedan en español (son para depurar).
7. Comentarios, docstrings y commits: siguen en español.

## 4. Trampas detectadas

- **Constantes de módulo evaluadas al importar**: `AUDIO_INPUT_FILTER` ("Todos los archivos"),
  `_SORT_MODES`, `SongInfoDialog.UNKNOWN` ("Desconocido"), `TRACK_SUGGESTIONS`, etc. Si se llama
  `tr()` ahí, se evalúa antes de cargar el idioma (los imports de `main.py` van primero). Regla:
  **la constante guarda el español y `tr()` se llama al usarla**. Para que el extractor las
  encuentre, marcarlas con un no-op `N_("texto")` (convención gettext).
- **f-strings**: no sirven como clave. `f"Separando {song}…"` pasa a
  `tr("Separando {song}…").format(song=song)`. Placeholders con nombre, nunca posicionales (el
  orden de las palabras cambia entre idiomas).
- **Plurales**: pocos casos ("1 canción" / "N canciones"). Resolver con dos claves explícitas,
  sin librería de plurales.
- **Alias de tags de la cola** (`_TAG_TRACK_ALIASES`, `audio_player.py:1626`): son lo que el
  usuario escribe para mutear pistas ("voz", "bajo"...). Agregar alias en los tres idiomas
  (`drums`, `vocals`, `bass`, `other`, `bateria`, `voz`, `baixo`, `outros`...) y aceptarlos
  **siempre**, sin importar el idioma activo (las tags pueden venir del móvil o de otra sesión).
  `TRACK_SUGGESTIONS` (`dialogs.py:549`) se muestra en el idioma activo.
- **Mensajes desde workers** (`dependencies.status`, errores de `demucs_worker`,
  `ytdlp_download_worker`): se traducen en el punto donde se emiten; seguro porque el idioma no
  cambia en caliente.
- **Ancho de textos**: portugués e inglés cambian largos (portugués suele ser más largo).
  Diálogos con `setFixedSize` en `BaseDialog`, pestañas con `min-width` en QSS (macOS), botones de
  la barra del editor con alto fijo. Revisar visualmente cada diálogo en pt.
- **Fuentes**: confirmar que Saira Stencil One y Righteous traen `ã õ ç â ê ô` (Space Mono y la
  fuente de símbolos no afectan). Si falta algún glifo, Qt cae a otra fuente y se ve mezclado.
- **Atajos con letra mnemónica** (`&Archivo`): si se usan, cada traducción define su propio `&`.

## 5. Paso a paso

### Paso 1 — Infraestructura `i18n.py`
- `load_language(code)`, `current_language()`, `tr(text)`, `N_(text)` (devuelve el texto tal cual).
- Carga `locales/<code>.json` vía `resource_path()` (para que funcione dentro del bundle).
- `SUPPORTED = {"es": "Español", "pt": "Português", "en": "English"}`; los nombres de idioma se
  muestran siempre en su propio idioma, nunca traducidos.

### Paso 2 — Preferencias `settings.json`
- `load_settings()` / `save_settings()` en `<data_dir>/settings.json`; archivo corrupto o
  inexistente → defaults, nunca crashea.
- Agregar `settings.json` a `.gitignore`.

### Paso 3 — Arranque (`main.py`)
- Justo después de crear `QApplication` (y antes del splash y de construir `AudioPlayer`): leer
  idioma → `load_language()`.
- Instalar `QTranslator` con `qtbase_<code>.qm` desde
  `QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)` para que Yes/No/Cancel, el
  menú contextual de `QLineEdit` y `QFileDialog` salgan en el idioma elegido.

### Paso 4 — Menú Opciones → Idioma
- Submenú con `_submenu()` y tres acciones con `_add_action(..., checkable=True)` dentro de un
  `QActionGroup` exclusivo; marcada la activa.
- Al cambiar: `save_settings()` + `QMessageBox` "Se aplicará al reiniciar PlayIt".

### Paso 5 — Envolver cadenas, por archivo (un commit por archivo)
Orden sugerido, de más visible a menos:
1. `audio_player.py` (menús, barra de estado, toolbar de playlist, mensajes)
2. `dialogs.py`
3. `lyrics_sync_editor.py`
4. `dependencies.py` y workers de instalación (`base_worker.py` y subclases)
5. `demucs_queue.py`, `demucs_worker.py`, `ytdlp_download_worker.py`, `lazy_resources.py`,
   `lyrics_api.py`, `ui_components.py`, `resources.py`, `update_check_worker.py`

En cada uno: `tr()` en textos visibles, `N_()` en constantes de módulo, f-strings a `.format()`,
y saltarse todo lo listado en la sección 3.

### Paso 6 — Script extractor
- `tools/extract_strings.py` (fuera del bundle): recorre los `.py` con `ast`, junta los literales
  de `tr()` y `N_()`, y actualiza `locales/en.json` / `pt.json` agregando claves nuevas con valor
  vacío y listando las huérfanas. Mantiene las traducciones a mano en sincronía con el código.

### Paso 7 — Traducir
- Llenar `en.json` y `pt.json` (~350-400 entradas cada uno). Ojo con portugués de Brasil vs
  Portugal: **recomiendo pt-BR** (mayor audiencia), mostrado como "Português (Brasil)".
- Rehacer `extract_name_btn.png` en tres versiones (`_en`, `_pt`) o, mejor, cambiarlo por un
  botón con texto + QSS (se borra la imagen y se traduce como cualquier otra cadena).

### Paso 8 — Empaquetado
- `PlayIt.spec`: agregar `locales/` a `datas`. Verificar que PyInstaller incluya los
  `qtbase_*.qm` de PyQt6 (el hook suele traerlos; si no, agregarlos explícitamente para es/pt/en).
- `build_windows.sh` y el workflow de CI no deberían requerir cambios (no hay paso de
  compilación); confirmar con un build.

### Paso 9 — Tests
Un solo `tests/test_i18n.py`:
- `tr()` sin traducción devuelve el español; con idioma cargado devuelve la traducción.
- Toda clave de `en.json`/`pt.json` existe en el código (no hay huérfanas).
- Los placeholders `{nombre}` de cada traducción coinciden con los de la clave (evita `KeyError`
  en `.format()` en tiempo de ejecución).
- Los tests existentes (que comparan textos en español) siguen pasando porque el idioma por
  defecto en tests es `es`: fijarlo en `tests/conftest.py`.

### Paso 10 — Verificación manual
- Arrancar en cada idioma y recorrer: menús, barra de estado, toolbar de playlist, cada diálogo
  (`SplitDialog`, lote, cola, info, corregir, descarga, remoto, about), editor de sincronización,
  pantalla completa de letras (toast de pistas), mensajes de dependencias.
- Revisar textos cortados en pt, sobre todo en macOS.
- Confirmar que el móvil sigue funcionando igual con la app en inglés (estado, cola, tags).

### Paso 11 — Documentación
- `README.md`: mencionar el selector de idioma. Traducir el README queda fuera de este plan.
- Actualizar `CLAUDE.md` (privado) con la regla: "todo texto visible pasa por `tr()`; constantes
  con `N_()`; lo de la sección 3 no se traduce".

## 6. Fuera de alcance

- i18n de PlayIt Mobile (proyecto aparte).
- Traducir README / `DOCUMENTACION_FUNCIONAL.md`.
- Cambio de idioma en caliente (ver 2.2).
- Más idiomas: el mecanismo los admite agregando un JSON y una entrada en `SUPPORTED`.

## 7. Estimación

| Paso | Esfuerzo |
|---|---|
| 1-4 infraestructura + menú | bajo (~1 sesión) |
| 5 envolver cadenas | alto: es el grueso, mecánico pero extenso (~350-400 cadenas) |
| 6 extractor | bajo |
| 7 traducción | medio |
| 8-11 build, tests, verificación, docs | medio |
