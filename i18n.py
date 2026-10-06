"""Traducción de la UI. El texto en español es la clave: `tr()` devuelve la
traducción del idioma activo y, si no la hay, el propio español.

El idioma se fija al arrancar (`load_language`) y no cambia en caliente, así
que `tr()` es seguro de llamar desde los hilos de los workers."""
import json
import logging
from pathlib import Path

from resources import resource_path

logger = logging.getLogger(__name__)

# Cada idioma se muestra con su propio nombre, nunca traducido.
SUPPORTED = {"es": "Español", "pt": "Português (Brasil)", "en": "English"}
DEFAULT_LANGUAGE = "en"  # el de quien no tiene es/pt/en en su sistema

_language = "es"
_strings: dict[str, str] = {}


def detect_system_language() -> str:
    """Idioma del sistema si está soportado; si no, DEFAULT_LANGUAGE."""
    from PyQt6.QtCore import QLocale
    code = QLocale.system().name().split("_")[0]
    return code if code in SUPPORTED else DEFAULT_LANGUAGE


def load_language(code: str) -> str:
    """Activa `code` y devuelve el que quedó activo (es si no se reconoce).
    Un JSON ausente o corrupto deja el español, nunca lanza."""
    global _language, _strings
    if code not in SUPPORTED:
        code = "es"
    _strings = {}
    if code != "es":
        try:
            path = Path(resource_path(f"locales/{code}.json"))
            _strings = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("No se pudo cargar el idioma %s: %s", code, e)
    _language = code
    return code


def current_language() -> str:
    return _language


def qlocale():
    """QLocale del idioma activo: fechas y días en el idioma de la app, no en
    el del sistema operativo (strftime usa este último)."""
    from PyQt6.QtCore import QLocale
    return QLocale("pt_BR" if _language == "pt" else _language)


def tr(text: str) -> str:
    """Traducción de `text` (español) o el mismo texto si falta."""
    return _strings.get(text) or text


def N_(text: str) -> str:
    """Marca una cadena para el extractor sin traducirla: para constantes de
    módulo, que se evalúan al importar, antes de cargar el idioma. Se llama
    `tr()` sobre la constante en el punto de uso."""
    return text
