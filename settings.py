"""Preferencias del usuario en <data_dir>/settings.json (idioma, por ahora).
Archivo ausente o corrupto = valores por defecto; nunca lanza."""
import json
import logging

from platform_utils import get_data_dir

logger = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads((get_data_dir() / SETTINGS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("settings.json ilegible, uso valores por defecto: %s", e)
        return {}


def save_setting(key: str, value) -> None:
    """Guarda una sola clave conservando las demás."""
    data = load_settings()
    data[key] = value
    try:
        (get_data_dir() / SETTINGS_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error("No se pudo guardar settings.json: %s", e)
