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

"""Servidor HTTP del modo remoto (control desde PlayIt Mobile).

El teléfono es el cliente; el Desktop levanta este servidor en la LAN y
expone cinco comandos de reproducción más la lista de canciones (solo
metadatos: artista, título, duración). El audio nunca sale de la PC.

Regla que no se negocia: los handlers corren en hilos del servidor, que
**no** son el hilo GUI de Qt. Nunca tocan widgets ni la playlist viva:

- comandos hacia adentro → `RemoteBridge.command.emit()` (Qt entrega el
  slot en el hilo GUI vía QueuedConnection automática);
- estado hacia afuera → el hilo GUI empuja un dict plano con
  `publish_state()` / `publish_playlist()` bajo Lock; el handler devuelve
  una copia.
"""

import io
import ipaddress
import json
import logging
import os
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal

from platform_utils import get_data_dir

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
DEFAULT_PORT = 8770
PORT_RANGE = range(DEFAULT_PORT, DEFAULT_PORT + 10)
MAX_BODY = 1024
# Corta conexiones keep-alive muertas (teléfono fuera de cobertura) para no
# dejar hilos del servidor colgados esperando bytes que no llegan.
CONN_TIMEOUT = 10

COMMANDS = ("play_pause", "stop", "next", "prev", "repeat", "play_index",
            "set_mute", "set_volume", "set_master_volume", "set_auto_unmute")
# Comandos que no tienen sentido con la playlist vacía → 409. El mezclador no
# está: mutear la voz o bajar el bajo son ajustes que valen antes de cargar
# nada, igual que mover los sliders con la ventana recién abierta.
NEEDS_PLAYLIST = ("play_pause", "next", "prev", "play_index")

# Pistas que acepta el mezclador. Duplica `TRACK_NAMES` de audio_player a
# propósito: importarlo desde acá sería un ciclo (audio_player importa este
# módulo) por cuatro strings que no cambian.
MIXER_TRACKS = ("drums", "vocals", "bass", "other")

TOKEN_FILE = "remote_token.json"
TOKEN_BYTES = 16                    # 32 caracteres hex

# Portadas: lado máximo en píxeles y tope de la caché en memoria. Una
# cover.png de 1500x1500 son ~2 MB y el móvil la dibuja a 64 px; 256 px en
# JPEG deja el envío en decenas de KB.
COVER_MAX_PX = 256
COVER_QUALITY = 80
COVER_CACHE_MAX = 64
COVER_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

# Descubrimiento: el móvil manda este texto por broadcast UDP al mismo número
# de puerto que la API TCP y el Desktop contesta unicast con su dirección.
# Sirve para reencontrar la PC cuando DHCP le cambió la IP.
DISCOVERY_PROBE = b"PLAYIT?"
DISCOVERY_MAX_PROBE = 64        # la sonda real son 9 bytes


def lan_ip() -> str:
    """IP de la interfaz que sale a la red.

    UDP `connect` solo fija la ruta en el socket: no envía un solo byte ni
    necesita que el destino exista.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_private(addr: str) -> bool:
    """True solo para direcciones de red privada (incluye loopback)."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def pairing_payload(ip: str, port: int, token: str, name: str) -> str:
    """Texto que se codifica en el QR (y que el móvil parsea al emparejar)."""
    return json.dumps({"v": PROTOCOL_VERSION, "h": ip, "p": port,
                       "t": token, "n": name}, separators=(",", ":"))


def format_token(token: str) -> str:
    """Token en grupos de 4 para poder dictarlo/teclearlo sin perderse."""
    return " ".join(token[i:i + 4] for i in range(0, len(token), 4))


# ── Token persistente ────────────────────────────────────────────────────
# El móvil guarda el token para reconectarse solo; si el Desktop generara uno
# nuevo en cada arranque, esa reconexión nunca funcionaría y habría que volver
# a escanear el QR todos los días.

def new_token() -> str:
    return secrets.token_hex(TOKEN_BYTES)


def is_valid_token(token) -> bool:
    if not isinstance(token, str) or len(token) != TOKEN_BYTES * 2:
        return False
    return all(c in "0123456789abcdef" for c in token)


def token_path() -> Path:
    return get_data_dir() / TOKEN_FILE


def load_token(path: Path) -> str:
    """Token guardado, o "" si no existe / está corrupto."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    token = data.get("token") if isinstance(data, dict) else None
    return token if is_valid_token(token) else ""


def save_token(path: Path, token: str) -> bool:
    """Guarda el token con permisos restrictivos. False si no se pudo."""
    try:
        path.write_text(json.dumps({"v": PROTOCOL_VERSION, "token": token}),
                        encoding="utf-8")
        if os.name == "posix":
            path.chmod(0o600)     # es una credencial, no un archivo más
        return True
    except OSError as exc:
        logger.warning("No se pudo guardar el token remoto: %s", exc)
        return False


# ── Portadas ─────────────────────────────────────────────────────────────

def find_cover(folder: Path) -> Path | None:
    """Imagen de portada dentro de la carpeta de la canción.

    Mismo orden que `LazyImageManager.load_cover_lazy`: primero el cover.png
    que escribe DemucsWorker, después cualquier otra imagen suelta. No se
    extrae de los MP3: eso requeriría mutagen en el hilo HTTP y, cuando el
    archivo original traía carátula, el cover.png ya existe.
    """
    try:
        cover = folder / "cover.png"
        if cover.is_file():
            return cover
        for item in sorted(folder.iterdir()):
            if item.is_file() and item.suffix.lower() in COVER_EXTS:
                return item
    except OSError:
        return None
    return None


def cover_jpeg(folder: Path, max_px: int = COVER_MAX_PX) -> bytes | None:
    """Portada reducida a JPEG, o None si la canción no tiene ninguna."""
    path = find_cover(folder)
    if path is None:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_px, max_px))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=COVER_QUALITY)
            return buffer.getvalue()
    except (OSError, ValueError) as exc:
        logger.warning("No se pudo leer la portada %s: %s", path, exc)
        return None


def discovery_reply(ip: str, tcp_port: int, name: str) -> bytes:
    """Respuesta a una sonda de descubrimiento.

    **Sin token**: un broadcast lo escucha toda la red, así que esto solo dice
    "acá hay un PlayIt"; el emparejamiento sigue necesitando el QR o el código
    tecleado. `p` es el puerto TCP **real**, que puede no ser el 8770 si estaba
    ocupado.
    """
    return json.dumps({"v": PROTOCOL_VERSION, "h": ip, "p": tcp_port,
                       "n": name}, separators=(",", ":")).encode()


class DiscoveryResponder:
    """Contesta sondas de descubrimiento en UDP. Un hilo, un socket."""

    def __init__(self, tcp_port: int, name: str, udp_port: int = DEFAULT_PORT):
        self.tcp_port = tcp_port
        self.name = name
        self.udp_port = udp_port
        self._socket = None
        self._thread = None
        self._running = False

    def start(self) -> bool:
        """True si quedó escuchando. Un fallo no es fatal: se pierde el
        descubrimiento, no el control remoto."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.udp_port))
            sock.settimeout(0.5)      # para poder frenar el hilo
        except OSError as exc:
            logger.warning("Descubrimiento UDP desactivado: %s", exc)
            return False
        self._socket = sock
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True,
                                        name="PlayItDiscovery")
        self._thread.start()
        return True

    def _serve(self):
        while self._running:
            try:
                data, addr = self._socket.recvfrom(DISCOVERY_MAX_PROBE)
            except socket.timeout:
                continue
            except OSError:
                break
            # El móvil manda dos sondas separadas 150 ms (la primera se pierde
            # mientras despierta la radio Wi-Fi): se contestan las dos, él
            # deduplica por (host, puerto).
            if not data.startswith(DISCOVERY_PROBE) or not is_private(addr[0]):
                continue
            try:
                self._socket.sendto(
                    discovery_reply(lan_ip(), self.tcp_port, self.name), addr)
            except OSError as exc:
                logger.warning("No se pudo responder la sonda: %s", exc)

    def stop(self):
        self._running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._thread = None


class RemoteBridge(QObject):
    """Único punto de contacto entre los hilos HTTP y el hilo GUI."""

    command = pyqtSignal(str, object)   # cmd, arg
    # El móvil llama /api/hello al emparejarse: sirve para cerrar solo el
    # diálogo del QR. Lleva la IP del teléfono, para poder mostrarla.
    paired = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._state: dict = {}
        self._playlist: dict = {"rev": 0, "items": []}
        # Carpetas de cada canción, paralelas a items. Solo para resolver
        # /api/cover: las rutas del disco nunca se serializan al móvil.
        self._folders: list = []
        self._cover_cache: dict = {}
        self.token = ""
        self.name = socket.gethostname()
        # False mientras el servidor se está apagando → responde 503
        self.active = True

    def publish_state(self, state: dict):
        with self._lock:
            self._state = state

    def publish_playlist(self, rev: int, items: list, folders: list | None = None):
        with self._lock:
            self._playlist = {"rev": rev, "items": items}
            self._folders = list(folders or [])

    def snapshot_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def snapshot_playlist(self) -> dict:
        with self._lock:
            return dict(self._playlist)

    def playlist_count(self) -> int:
        with self._lock:
            return len(self._playlist["items"])

    def cover(self, index: int) -> bytes | None:
        """Portada de una canción, cacheada por (carpeta, fecha de la imagen).

        Corre en el hilo HTTP: solo toca disco y la caché propia, nunca la
        playlist viva. El decodificado queda fuera del lock para no serializar
        peticiones simultáneas de portadas distintas.
        """
        with self._lock:
            if not 0 <= index < len(self._folders):
                return None
            folder = Path(self._folders[index])

        path = find_cover(folder)
        if path is None:
            return None
        try:
            key = (str(path), path.stat().st_mtime_ns)
        except OSError:
            return None

        with self._lock:
            if key in self._cover_cache:
                return self._cover_cache[key]

        data = cover_jpeg(folder)
        if data is None:
            return None

        with self._lock:
            if len(self._cover_cache) >= COVER_CACHE_MAX:
                self._cover_cache.clear()
            self._cover_cache[key] = data
        return data


class _Handler(BaseHTTPRequestHandler):
    bridge: RemoteBridge = None          # inyectado por RemoteServer
    protocol_version = "HTTP/1.1"
    timeout = CONN_TIMEOUT

    def log_message(self, *args):        # sin ruido en consola
        pass

    # ── helpers ──────────────────────────────────────────────────────────
    def _send(self, code: int, payload: dict):
        self._send_bytes(code, "application/json",
                         json.dumps(payload).encode())

    def _send_bytes(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        bridge = self.bridge
        if bridge is None or not bridge.active:
            self._send(503, {"error": "modo remoto desactivado"})
            return False
        if not is_private(self.client_address[0]):
            self._send(403, {"error": "solo red local"})
            return False
        got = self.headers.get("X-PlayIt-Token", "")
        if not secrets.compare_digest(got, bridge.token):
            self._send(401, {"error": "token invalido"})
            return False
        return True

    def _read_command(self) -> dict | None:
        """Cuerpo del POST validado; None si ya se respondió un error."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "longitud invalida"})
            return None
        if length > MAX_BODY:
            self._send(400, {"error": "cuerpo muy grande"})
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            cmd = str(data["cmd"])
        except (ValueError, KeyError, TypeError):
            self._send(400, {"error": "json invalido"})
            return None
        if cmd not in COMMANDS:
            self._send(400, {"error": f"comando desconocido: {cmd}"})
            return None

        count = self.bridge.playlist_count()
        if cmd in NEEDS_PLAYLIST and count == 0:
            self._send(409, {"error": "playlist vacia"})
            return None

        if cmd == "play_index":
            index = data.get("index")
            # bool es subclase de int: un True no es un índice
            if not isinstance(index, int) or isinstance(index, bool) \
                    or not 0 <= index < count:
                self._send(400, {"error": "indice fuera de rango"})
                return None
            return {"cmd": cmd, "arg": index}
        if cmd == "repeat":
            value = data.get("value")
            return {"cmd": cmd, "arg": None if value is None else bool(value)}
        if cmd == "set_mute":
            track = data.get("track")
            if track not in MIXER_TRACKS:
                self._send(400, {"error": f"pista desconocida: {track}"})
                return None
            return {"cmd": cmd, "arg": (track, bool(data.get("value")))}
        if cmd == "set_auto_unmute":
            return {"cmd": cmd, "arg": bool(data.get("value"))}
        if cmd in ("set_volume", "set_master_volume"):
            # Absolutos y en enteros 0-100: un comando perdido se corrige solo
            # con el siguiente, y no hay redondeo de floats en el JSON.
            value = data.get("value")
            if not isinstance(value, int) or isinstance(value, bool) \
                    or not 0 <= value <= 100:
                self._send(400, {"error": "volumen fuera de rango"})
                return None
            if cmd == "set_master_volume":
                return {"cmd": cmd, "arg": value}
            track = data.get("track")
            if track not in MIXER_TRACKS:
                self._send(400, {"error": f"pista desconocida: {track}"})
                return None
            return {"cmd": cmd, "arg": (track, value)}
        return {"cmd": cmd, "arg": None}

    # ── rutas ────────────────────────────────────────────────────────────
    def do_GET(self):
        if not self._authorized():
            return
        route, _, query = self.path.partition("?")
        if route == "/api/hello":
            from version import __version__
            self._send(200, {"v": PROTOCOL_VERSION,
                             "name": self.bridge.name, "app": __version__})
            # Después de responder: el emparejamiento ya está hecho y el
            # teléfono no tiene que esperar al hilo GUI para recibirlo.
            self.bridge.paired.emit(self.client_address[0])
        elif route == "/api/state":
            self._send(200, self.bridge.snapshot_state())
        elif route == "/api/playlist":
            self._send(200, self.bridge.snapshot_playlist())
        elif route == "/api/cover":
            self._send_cover(query)
        else:
            self._send(404, {"error": "no existe"})

    def _send_cover(self, query: str):
        raw = urllib.parse.parse_qs(query).get("index", [""])[0]
        try:
            index = int(raw)
        except ValueError:
            self._send(400, {"error": "indice invalido"})
            return
        # Fuera de rango es 400, no 404: el 404 significa "esta canción no
        # tiene carátula", que para el móvil es un caso normal.
        if not 0 <= index < self.bridge.playlist_count():
            self._send(400, {"error": "indice fuera de rango"})
            return
        data = self.bridge.cover(index)
        if data is None:
            # Sin carátula es un caso normal, no un error: el móvil lo usa
            # para mostrar su propio hueco.
            self._send(404, {"error": "sin caratula"})
            return
        self._send_bytes(200, "image/jpeg", data)

    def do_POST(self):
        if not self._authorized():
            return
        if self.path.split("?", 1)[0] != "/api/command":
            self._send(404, {"error": "no existe"})
            return
        parsed = self._read_command()
        if parsed is None:
            return
        self.bridge.command.emit(parsed["cmd"], parsed["arg"])   # → hilo GUI
        self._send(200, {"ok": True})


class RemoteServer:
    """Arranca/detiene el `ThreadingHTTPServer` en un hilo daemon."""

    def __init__(self, bridge: RemoteBridge, token_file: Path | None = None,
                 discovery: bool = True, udp_port: int = DEFAULT_PORT):
        self.bridge = bridge
        self._httpd = None
        self._thread = None
        self._responder = None
        self._token_file = token_file if token_file is not None else token_path()
        self._discovery_enabled = discovery
        self._udp_port = udp_port
        self.port = 0

    def _resolve_token(self, rotate: bool) -> str:
        """Reusa el token guardado; genera (y guarda) uno nuevo si hace falta."""
        if not rotate:
            saved = load_token(self._token_file)
            if saved:
                return saved
        token = new_token()
        save_token(self._token_file, token)
        return token

    def start(self, rotate: bool = False) -> tuple[str, int, str]:
        """Levanta el servidor y devuelve (ip, puerto, token).

        Con `rotate=True` descarta el token guardado y emite uno nuevo, que es
        lo que hace "Generar nuevo código": desempareja los teléfonos previos.
        """
        self.bridge.token = self._resolve_token(rotate)
        self.bridge.active = True
        _Handler.bridge = self.bridge
        last = None
        for port in PORT_RANGE:
            try:
                self._httpd = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
                self.port = port
                break
            except OSError as exc:
                last = exc
        else:
            raise RuntimeError(
                f"ningún puerto libre entre {PORT_RANGE.start} y "
                f"{PORT_RANGE.stop - 1}: {last}"
            )
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True, name="PlayItRemote")
        self._thread.start()
        self._start_discovery()
        return lan_ip(), self.port, self.bridge.token

    def stop(self):
        self.bridge.active = False
        if self._responder is not None:
            self._responder.stop()
            self._responder = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None
        if _Handler.bridge is self.bridge:
            _Handler.bridge = None

    def _start_discovery(self):
        """Levanta el respondedor UDP; si no puede, sigue sin descubrimiento."""
        if not self._discovery_enabled:
            return
        responder = DiscoveryResponder(self.port, self.bridge.name,
                                       udp_port=self._udp_port)
        self._responder = responder if responder.start() else None
