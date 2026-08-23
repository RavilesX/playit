"""Tests del modo remoto: funciones puras, servidor HTTP real y el puente
con AudioPlayer.

El servidor se levanta en un puerto libre y se golpea con urllib desde
127.0.0.1 (loopback cuenta como privada). No hay red externa involucrada.
"""
import io
import json
import socket
import urllib.error
import urllib.request

import pytest

from remote_server import (
    COVER_MAX_PX,
    DISCOVERY_PROBE,
    PROTOCOL_VERSION,
    DiscoveryResponder,
    RemoteBridge,
    RemoteServer,
    cover_jpeg,
    discovery_reply,
    find_cover,
    format_token,
    is_private,
    is_valid_token,
    lan_ip,
    load_token,
    new_token,
    pairing_payload,
    save_token,
)


class TestFuncionesPuras:
    @pytest.mark.parametrize("addr", [
        "192.168.1.42", "10.0.0.5", "172.16.3.1", "172.31.255.254", "127.0.0.1",
    ])
    def test_privadas(self, addr):
        assert is_private(addr)

    @pytest.mark.parametrize("addr", [
        "8.8.8.8", "1.1.1.1", "172.32.0.1", "", "no-una-ip", "999.1.1.1",
    ])
    def test_no_privadas(self, addr):
        assert not is_private(addr)

    def test_lan_ip_devuelve_algo(self):
        ip = lan_ip()
        assert isinstance(ip, str) and ip

    def test_pairing_payload_round_trip(self):
        data = json.loads(pairing_payload("192.168.1.42", 8770, "ab" * 16, "PC"))
        assert data == {"v": PROTOCOL_VERSION, "h": "192.168.1.42", "p": 8770,
                        "t": "ab" * 16, "n": "PC"}

    def test_format_token_en_grupos_de_4(self):
        assert format_token("0123456789abcdef") == "0123 4567 89ab cdef"


@pytest.fixture
def token_file(tmp_path):
    """Token fuera del data dir real: los tests no tocan el del usuario."""
    return tmp_path / "remote_token.json"


@pytest.fixture
def free_udp_port():
    """Puerto UDP libre: el descubrimiento real usa el 8770 fijo y no puede
    compartirse entre tests que corren en el mismo equipo."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _make_server(bridge, token_file, **kwargs):
    """Servidor de test: sin descubrimiento UDP (el 8770 es uno solo para
    toda la suite) y con token descartable."""
    return RemoteServer(bridge, token_file=token_file, discovery=False,
                        **kwargs)


def _write_cover(folder, size=(500, 500), color=(200, 30, 90), name="cover.png"):
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(folder / name)
    return folder / name


@pytest.fixture
def server(app, token_file, tmp_path):
    """Servidor real con una playlist de 2 canciones publicada.

    La primera canción tiene portada en disco; la segunda no, para cubrir el
    404 que el móvil trata como caso normal.
    """
    con_portada = tmp_path / "Rush" / "YYZ"
    _write_cover(con_portada)
    sin_portada = tmp_path / "Rush" / "Tom Sawyer"
    sin_portada.mkdir(parents=True, exist_ok=True)

    bridge = RemoteBridge()
    bridge.name = "PC-Test"
    srv = _make_server(bridge, token_file)
    _, port, token = srv.start()
    bridge.publish_state({"v": 1, "state": "Detenido", "index": -1, "count": 2})
    bridge.publish_playlist(
        7,
        [
            {"i": 0, "artist": "Rush", "song": "YYZ", "duration": "4:25"},
            {"i": 1, "artist": "Rush", "song": "Tom Sawyer", "duration": "4:34"},
        ],
        [str(con_portada), str(sin_portada)],
    )
    yield bridge, port, token
    srv.stop()


def _request(port, path, token, method="GET", body=None):
    """Devuelve (código, dict). Los errores HTTP también traen JSON."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"X-PlayIt-Token": token} if token is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _request_raw(port, path, token):
    """Como _request pero devuelve (código, content-type, bytes)."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"X-PlayIt-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type"), exc.read()


class TestServidor:
    def test_sin_token_401(self, server):
        _, port, _ = server
        code, _body = _request(port, "/api/state", None)
        assert code == 401

    def test_token_incorrecto_401(self, server):
        _, port, _ = server
        code, _body = _request(port, "/api/state", "0" * 32)
        assert code == 401

    def test_hello(self, server):
        _, port, token = server
        code, body = _request(port, "/api/hello", token)
        assert code == 200
        assert body["v"] == PROTOCOL_VERSION
        assert body["name"] == "PC-Test"
        assert body["app"]

    def test_state_devuelve_el_snapshot(self, server):
        _, port, token = server
        code, body = _request(port, "/api/state", token)
        assert code == 200
        assert body["state"] == "Detenido"

    def test_playlist_con_rev(self, server):
        _, port, token = server
        code, body = _request(port, "/api/playlist", token)
        assert code == 200
        assert body["rev"] == 7
        assert [i["song"] for i in body["items"]] == ["YYZ", "Tom Sawyer"]

    def test_ruta_desconocida_404(self, server):
        _, port, token = server
        code, _body = _request(port, "/api/nada", token)
        assert code == 404

    def test_comando_desconocido_400(self, server):
        _, port, token = server
        code, _body = _request(port, "/api/command", token, "POST",
                               {"cmd": "autodestruir"})
        assert code == 400

    def test_json_invalido_400(self, server):
        _, port, token = server
        code, _body = _request(port, "/api/command", token, "POST", {"x": 1})
        assert code == 400

    def test_indice_fuera_de_rango_400(self, server):
        _, port, token = server
        code, _body = _request(port, "/api/command", token, "POST",
                               {"cmd": "play_index", "index": 99})
        assert code == 400

    def test_indice_booleano_400(self, server):
        """True es int en Python, pero no es un índice."""
        _, port, token = server
        code, _body = _request(port, "/api/command", token, "POST",
                               {"cmd": "play_index", "index": True})
        assert code == 400

    def test_playlist_vacia_409(self, app, token_file):
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, port, token = srv.start()
        try:
            code, _body = _request(port, "/api/command", token, "POST",
                                   {"cmd": "next"})
            assert code == 409
        finally:
            srv.stop()

    def test_comando_emite_la_senal(self, server, qtbot):
        bridge, port, token = server
        with qtbot.waitSignal(bridge.command, timeout=3000) as blocker:
            code, body = _request(port, "/api/command", token, "POST",
                                  {"cmd": "play_index", "index": 1})
        assert (code, body) == (200, {"ok": True})
        assert blocker.args == ["play_index", 1]

    def test_repeat_con_valor(self, server, qtbot):
        bridge, port, token = server
        with qtbot.waitSignal(bridge.command, timeout=3000) as blocker:
            _request(port, "/api/command", token, "POST",
                     {"cmd": "repeat", "value": True})
        assert blocker.args == ["repeat", True]

    def test_repeat_sin_valor_es_toggle(self, server, qtbot):
        bridge, port, token = server
        with qtbot.waitSignal(bridge.command, timeout=3000) as blocker:
            _request(port, "/api/command", token, "POST", {"cmd": "repeat"})
        assert blocker.args == ["repeat", None]

    def test_tras_stop_el_puerto_queda_libre(self, app, token_file):
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, port, token = srv.start()
        srv.stop()
        # El puerto queda libre: la conexión ya no entra
        with pytest.raises(urllib.error.URLError):
            _request(port, "/api/state", token)

    def test_token_rotado_invalida_el_anterior(self, app, token_file):
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, _, viejo = srv.start()
        srv.stop()
        _, port, nuevo = srv.start(rotate=True)
        try:
            assert viejo != nuevo
            assert _request(port, "/api/state", viejo)[0] == 401
            assert _request(port, "/api/state", nuevo)[0] == 200
        finally:
            srv.stop()


class TestPuenteConElReproductor:
    def test_bump_incrementa_y_republica(self, player):
        player._remote_bridge = RemoteBridge()
        player._on_songs_loaded([
            {"artist": "A", "song": "1", "path": "/tmp/x", "duration": "1:00"},
        ])
        rev = player._playlist_rev
        assert rev > 0
        snap = player._remote_bridge.snapshot_playlist()
        assert snap["rev"] == rev
        assert snap["items"] == [
            {"i": 0, "artist": "A", "song": "1", "duration": "1:00"},
        ]
        player._remote_bridge = None

    def test_publish_state_sin_bridge_no_revienta(self, player):
        player._remote_bridge = None
        player._publish_remote_state()
        player._publish_remote_playlist()

    def test_publish_state_refleja_la_playlist(self, player):
        player._remote_bridge = RemoteBridge()
        player._on_songs_loaded([
            {"artist": "Rush", "song": "YYZ", "path": "/tmp/x", "duration": "4:25"},
        ])
        player.current_index = 0
        player._publish_remote_state()
        state = player._remote_bridge.snapshot_state()
        assert state["artist"] == "Rush"
        assert state["song"] == "YYZ"
        assert state["count"] == 1
        assert state["state"] == player.playback_state
        player._remote_bridge = None

    def test_set_repeat_sincroniza_boton(self, player):
        player.set_repeat(True)
        assert player._repeat is True
        assert player.repeat_btn.isChecked()
        player.set_repeat(False)
        assert player._repeat is False
        assert not player.repeat_btn.isChecked()

    def test_comando_remoto_repeat(self, player):
        player.set_repeat(False)
        player._handle_remote_command("repeat", None)
        assert player._repeat is True
        player._handle_remote_command("repeat", False)
        assert player._repeat is False

    def test_comando_remoto_con_playlist_vacia_no_revienta(self, player):
        for cmd in ("next", "prev", "stop", "play_index"):
            player._handle_remote_command(cmd, 0)


class TestTokenPersistente:
    """El móvil guarda el token para reconectar solo: si el Desktop generara
    uno nuevo en cada arranque, esa reconexión no serviría de nada."""

    def test_new_token_es_valido(self):
        token = new_token()
        assert is_valid_token(token)
        assert new_token() != token

    @pytest.mark.parametrize("bad", [
        "", "xyz", "0" * 31, "0" * 33, "g" * 32, "AB" * 16, None, 123,
    ])
    def test_tokens_invalidos(self, bad):
        assert not is_valid_token(bad)

    def test_guardar_y_leer(self, token_file):
        token = new_token()
        assert save_token(token_file, token)
        assert load_token(token_file) == token

    def test_archivo_inexistente(self, token_file):
        assert load_token(token_file) == ""

    def test_archivo_corrupto(self, token_file):
        token_file.write_text("{no es json", encoding="utf-8")
        assert load_token(token_file) == ""

    def test_token_de_forma_invalida_se_descarta(self, token_file):
        token_file.write_text(json.dumps({"token": "corto"}), encoding="utf-8")
        assert load_token(token_file) == ""

    def test_reinicio_conserva_el_token(self, app, token_file):
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, _, primero = srv.start()
        srv.stop()

        # Otro proceso: bridge y servidor nuevos, mismo archivo
        srv2 = _make_server(RemoteBridge(), token_file)
        _, port, segundo = srv2.start()
        try:
            assert segundo == primero
            assert _request(port, "/api/state", primero)[0] == 200
        finally:
            srv2.stop()

    def test_rotate_reescribe_el_archivo(self, app, token_file):
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, _, viejo = srv.start()
        srv.stop()
        _, _, nuevo = srv.start(rotate=True)
        srv.stop()
        assert nuevo != viejo
        assert load_token(token_file) == nuevo


class TestPortadas:
    def test_find_cover_prefiere_cover_png(self, tmp_path):
        _write_cover(tmp_path, name="portada.jpg")
        _write_cover(tmp_path)
        assert find_cover(tmp_path).name == "cover.png"

    def test_find_cover_acepta_otra_imagen(self, tmp_path):
        _write_cover(tmp_path, name="folder.jpg")
        assert find_cover(tmp_path).name == "folder.jpg"

    def test_find_cover_sin_imagenes(self, tmp_path):
        (tmp_path / "other.mp3").write_bytes(b"no soy imagen")
        assert find_cover(tmp_path) is None

    def test_find_cover_carpeta_inexistente(self, tmp_path):
        assert find_cover(tmp_path / "no-existe") is None

    def test_cover_jpeg_reduce(self, tmp_path):
        from PIL import Image

        _write_cover(tmp_path, size=(500, 500))
        data = cover_jpeg(tmp_path)
        assert data is not None
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == "JPEG"
            assert max(img.size) <= COVER_MAX_PX

    def test_cover_jpeg_sin_portada(self, tmp_path):
        assert cover_jpeg(tmp_path) is None

    def test_cover_jpeg_archivo_roto(self, tmp_path):
        (tmp_path / "cover.png").write_bytes(b"no soy un png")
        assert cover_jpeg(tmp_path) is None

    def test_endpoint_devuelve_jpeg(self, server):
        _, port, token = server
        code, ctype, body = _request_raw(port, "/api/cover?index=0", token)
        assert code == 200
        assert ctype == "image/jpeg"
        assert body.startswith(b"\xff\xd8")

    def test_endpoint_sin_portada_404(self, server):
        _, port, token = server
        code, _ctype, _body = _request_raw(port, "/api/cover?index=1", token)
        assert code == 404

    def test_endpoint_indice_fuera_de_rango_400(self, server):
        """400, no 404: el 404 quiere decir "esta canción no tiene carátula",
        que para el móvil es un caso normal."""
        _, port, token = server
        assert _request_raw(port, "/api/cover?index=99", token)[0] == 400

    def test_endpoint_indice_invalido_400(self, server):
        _, port, token = server
        assert _request_raw(port, "/api/cover?index=abc", token)[0] == 400

    def test_endpoint_sin_indice_400(self, server):
        _, port, token = server
        assert _request_raw(port, "/api/cover", token)[0] == 400

    def test_endpoint_exige_token(self, server):
        _, port, _token = server
        assert _request_raw(port, "/api/cover?index=0", "0" * 32)[0] == 401

    def test_la_playlist_no_expone_rutas(self, server):
        """Las carpetas son solo para resolver la portada del lado del PC."""
        _, port, token = server
        _code, body = _request(port, "/api/playlist", token)
        assert "path" not in json.dumps(body)
        for item in body["items"]:
            assert set(item) == {"i", "artist", "song", "duration"}

    def test_cache_evita_recodificar(self, app, tmp_path):
        bridge = RemoteBridge()
        folder = tmp_path / "song"
        _write_cover(folder)
        bridge.publish_playlist(1, [{"i": 0}], [str(folder)])

        primero = bridge.cover(0)
        assert primero is not None
        # Mismo objeto: se devolvió de la caché, no se volvió a codificar
        assert bridge.cover(0) is primero

    def test_cache_se_invalida_al_cambiar_la_portada(self, app, tmp_path):
        bridge = RemoteBridge()
        folder = tmp_path / "song"
        _write_cover(folder, color=(10, 10, 10))
        bridge.publish_playlist(1, [{"i": 0}], [str(folder)])
        primero = bridge.cover(0)

        # La clave incluye el mtime: reescribir la portada la invalida
        _write_cover(folder, color=(240, 240, 240))
        segundo = bridge.cover(0)
        assert segundo is not None and segundo != primero

    def test_cover_sin_carpetas_publicadas(self, app):
        bridge = RemoteBridge()
        bridge.publish_playlist(1, [{"i": 0}])
        assert bridge.cover(0) is None


class TestDescubrimiento:
    """Sondas UDP: el móvil las manda por broadcast cuando el token guardado
    apunta a una IP que DHCP ya reasignó."""

    PROBE = b"PLAYIT?v1"

    @staticmethod
    def _probe(udp_port, payload=PROBE, timeout=2.0):
        """Manda una sonda a loopback y devuelve la respuesta decodificada."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(payload, ("127.0.0.1", udp_port))
            data, _addr = sock.recvfrom(512)
            return json.loads(data)
        finally:
            sock.close()

    @pytest.fixture
    def responder(self, free_udp_port):
        r = DiscoveryResponder(8779, "PC-Test", udp_port=free_udp_port)
        assert r.start()
        yield r, free_udp_port
        r.stop()

    def test_la_sonda_del_movil_calza_con_el_prefijo(self):
        """El móvil manda "PLAYIT?v1"; el Desktop acepta por prefijo para que
        una v2 futura siga siendo respondida."""
        assert self.PROBE.startswith(DISCOVERY_PROBE)

    def test_reply_no_lleva_el_token(self):
        """Un broadcast lo escucha toda la red: el token no puede ir ahí."""
        data = json.loads(discovery_reply("192.168.1.42", 8771, "PC"))
        assert data == {"v": PROTOCOL_VERSION, "h": "192.168.1.42",
                        "p": 8771, "n": "PC"}
        assert "t" not in data

    def test_responde_la_sonda(self, responder):
        _r, port = responder
        data = self._probe(port)
        assert data["v"] == PROTOCOL_VERSION
        assert data["n"] == "PC-Test"

    def test_devuelve_el_puerto_tcp_real(self, responder):
        """Si el 8770 estaba ocupado y la API cayó al 8779, eso es lo que
        tiene que viajar, no la constante."""
        _r, port = responder
        assert self._probe(port)["p"] == 8779

    def test_contesta_las_dos_sondas(self, responder):
        """El móvil manda dos separadas 150 ms: la primera suele perderse
        mientras despierta la radio Wi-Fi."""
        _r, port = responder
        assert self._probe(port)["p"] == self._probe(port)["p"] == 8779

    def test_ignora_datagramas_ajenos(self, responder):
        _r, port = responder
        with pytest.raises(socket.timeout):
            self._probe(port, payload=b"hola?", timeout=0.8)

    def test_ignora_sonda_gigante(self, responder):
        """recvfrom corta en 64 bytes: el prefijo queda fuera y no se contesta."""
        _r, port = responder
        with pytest.raises(socket.timeout):
            self._probe(port, payload=b"x" * 200 + self.PROBE, timeout=0.8)

    def test_bind_ocupado_no_es_fatal(self, app, token_file, free_udp_port):
        """Otro proceso con el puerto UDP tomado: se pierde el
        descubrimiento, no el control remoto."""
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("0.0.0.0", free_udp_port))
        # Sin SO_REUSEADDR del lado del bloqueador el segundo bind falla
        try:
            srv = RemoteServer(RemoteBridge(), token_file=token_file,
                               udp_port=free_udp_port)
            _, port, token = srv.start()
            try:
                assert _request(port, "/api/state", token)[0] == 200
            finally:
                srv.stop()
        finally:
            blocker.close()

    def test_stop_libera_el_puerto(self, app, token_file, free_udp_port):
        srv = RemoteServer(RemoteBridge(), token_file=token_file,
                           udp_port=free_udp_port)
        srv.start()
        assert srv._responder is not None
        srv.stop()
        with pytest.raises(socket.timeout):
            self._probe(free_udp_port, timeout=0.8)


class TestContratoDelSnapshot:
    """El móvil lee estas claves y ninguna otra; los nombres y los tres
    valores de `state` son literales. Un cambio acá rompe el control remoto
    en silencio, sin ningún error."""

    CLAVES_STATE = {"v", "state", "index", "artist", "song", "position_ms",
                    "duration_ms", "repeat", "count", "rev",
                    "master_volume", "volumes", "mute", "auto_unmute"}

    def _snapshot(self, player):
        player._remote_bridge = RemoteBridge()
        try:
            player._publish_remote_state()
            return player._remote_bridge.snapshot_state()
        finally:
            player._remote_bridge = None

    def test_claves_exactas(self, player):
        assert set(self._snapshot(player)) == self.CLAVES_STATE

    def test_tipos(self, player):
        # Import diferido: audio_player arrastra Qt y este módulo también se
        # importa para los tests puros del servidor.
        from audio_player import TRACK_NAMES

        state = self._snapshot(player)
        assert state["v"] == PROTOCOL_VERSION
        assert isinstance(state["state"], str)
        assert isinstance(state["index"], int)
        assert isinstance(state["artist"], str)
        assert isinstance(state["song"], str)
        assert isinstance(state["position_ms"], int)
        assert isinstance(state["duration_ms"], int)
        assert isinstance(state["repeat"], bool)
        assert isinstance(state["count"], int)
        assert isinstance(state["rev"], int)
        assert isinstance(state["master_volume"], int)
        assert set(state["volumes"]) == set(TRACK_NAMES)
        assert all(isinstance(v, int) and 0 <= v <= 100
                   for v in state["volumes"].values())
        assert set(state["mute"]) == set(TRACK_NAMES)
        assert all(isinstance(v, bool) for v in state["mute"].values())
        assert isinstance(state["auto_unmute"], bool)

    @pytest.mark.parametrize("estado", ["Detenido", "Pausada", "Activa"])
    def test_los_tres_estados_viajan_literales(self, player, estado):
        """Cualquier otra cadena el móvil la lee como Detenido."""
        previo = player.playback_state
        try:
            player.playback_state = estado
            assert self._snapshot(player)["state"] == estado
        finally:
            player.playback_state = previo

    def test_items_de_playlist_usan_i(self, player):
        player._remote_bridge = RemoteBridge()
        try:
            player._on_songs_loaded([
                {"artist": "A", "song": "1", "path": "/tmp/x", "duration": "1:00"},
            ])
            items = player._remote_bridge.snapshot_playlist()["items"]
            assert set(items[0]) == {"i", "artist", "song", "duration"}
        finally:
            player._remote_bridge = None

    def test_serializa_a_json(self, player):
        """El handler hace json.dumps sin escaparse de errores de tipo."""
        json.dumps(self._snapshot(player))

    def test_target_adelanta_activa_sin_tocar_el_estado_real(self, player):
        """_publish_remote_target miente a propósito mientras cargan los
        stems; el estado real del reproductor no se toca."""
        player._remote_bridge = RemoteBridge()
        try:
            player.playback_state = "Detenido"
            player._publish_remote_target()
            snap = player._remote_bridge.snapshot_state()
            assert snap["state"] == "Activa"
            assert snap["position_ms"] == 0
            assert player.playback_state == "Detenido"
        finally:
            player._remote_bridge = None


class TestMuteRemoteable:
    """set_mute es la fuente de verdad: toggle_mute depende de self.sender()
    y un comando remoto entra por señal, no por un clic."""

    def test_set_mute_actualiza_estado_e_icono(self, player):
        player.set_mute("vocals", True)
        assert player.mute_states["vocals"] is True
        assert player.vocals_btn.isChecked()
        player.set_mute("vocals", False)
        assert player.mute_states["vocals"] is False
        assert not player.vocals_btn.isChecked()

    def test_set_mute_ignora_pistas_desconocidas(self, player):
        antes = dict(player.mute_states)
        player.set_mute("guitarra", True)
        assert player.mute_states == antes

    def test_toggle_mute_sin_boton_no_hace_nada(self, player):
        """Llamado fuera de un clic (que es como llegaría un comando remoto
        si se conectara directo), no puede resolver la pista."""
        antes = dict(player.mute_states)
        player.toggle_mute()
        assert player.mute_states == antes

    def test_click_del_boton_sigue_funcionando(self, player):
        antes = player.mute_states["drums"]
        player.drums_btn.click()
        assert player.mute_states["drums"] is not antes
        player.drums_btn.click()
        assert player.mute_states["drums"] is antes


class TestMezcladorRemoto:
    """Volumen y mute desde el móvil (PLAN_REMOTO §8).

    Son aditivos: no suben PROTOCOL_VERSION. El móvil decide si mostrar los
    controles por la presencia de las claves en el snapshot, así que lo que
    se prueba acá es que viajen y que los comandos se validen antes de llegar
    al hilo GUI.
    """

    @pytest.mark.parametrize("body,esperado", [
        ({"cmd": "set_mute", "track": "vocals", "value": True},
         ["set_mute", ("vocals", True)]),
        ({"cmd": "set_mute", "track": "drums", "value": False},
         ["set_mute", ("drums", False)]),
        ({"cmd": "set_volume", "track": "bass", "value": 60},
         ["set_volume", ("bass", 60)]),
        ({"cmd": "set_volume", "track": "other", "value": 0},
         ["set_volume", ("other", 0)]),
        ({"cmd": "set_master_volume", "value": 30},
         ["set_master_volume", 30]),
        ({"cmd": "set_auto_unmute", "value": True},
         ["set_auto_unmute", True]),
        ({"cmd": "set_auto_unmute", "value": False},
         ["set_auto_unmute", False]),
    ])
    def test_comandos_validos_llegan_al_puente(self, server, qtbot, body,
                                               esperado):
        bridge, port, token = server
        with qtbot.waitSignal(bridge.command, timeout=3000) as blocker:
            code, data = _request(port, "/api/command", token,
                                  method="POST", body=body)
        assert (code, data) == (200, {"ok": True})
        assert blocker.args == esperado

    @pytest.mark.parametrize("body", [
        {"cmd": "set_mute", "track": "guitarra", "value": True},
        {"cmd": "set_volume", "track": "guitarra", "value": 50},
        {"cmd": "set_volume", "value": 50},
        {"cmd": "set_volume", "track": "bass", "value": 101},
        {"cmd": "set_volume", "track": "bass", "value": -1},
        {"cmd": "set_volume", "track": "bass", "value": "alto"},
        {"cmd": "set_volume", "track": "bass", "value": 50.5},
        # bool es subclase de int: True no es un volumen
        {"cmd": "set_master_volume", "value": True},
        {"cmd": "set_master_volume"},
    ])
    def test_comandos_invalidos_son_400(self, server, qtbot, body):
        bridge, port, token = server
        recibidos = []
        bridge.command.connect(lambda cmd, arg: recibidos.append((cmd, arg)))

        code, data = _request(port, "/api/command", token,
                              method="POST", body=body)
        assert code == 400
        assert "error" in data
        # Nada cruzó al hilo GUI: la validación es del lado del handler.
        qtbot.wait(100)
        assert recibidos == []

    def test_el_mezclador_no_necesita_playlist(self, token_file):
        """Bajar el bajo antes de cargar nada es legítimo: 409 es solo para
        los comandos de reproducción."""
        bridge = RemoteBridge()
        srv = _make_server(bridge, token_file)
        _, port, token = srv.start()
        try:
            bridge.publish_playlist(0, [], [])
            code, _ = _request(port, "/api/command", token, method="POST",
                               body={"cmd": "set_volume", "track": "bass",
                                     "value": 10})
            assert code == 200
            code, _ = _request(port, "/api/command", token, method="POST",
                               body={"cmd": "next"})
            assert code == 409
        finally:
            srv.stop()

    def test_volumen_remoto_mueve_el_slider(self, player):
        player._handle_remote_command("set_volume", ("bass", 40))
        assert player._track_sliders["bass"].value() == 40
        assert player.individual_volumes["bass"] == pytest.approx(0.4)

    def test_volumen_general_remoto_mueve_el_dial(self, player):
        player._handle_remote_command("set_master_volume", 35)
        assert player.volume_dial.value() == 35
        assert player.volume == 35

    def test_mute_remoto_mueve_el_boton(self, player):
        player._handle_remote_command("set_mute", ("vocals", True))
        assert player.mute_states["vocals"] is True
        assert player.vocals_btn.isChecked()
        player._handle_remote_command("set_mute", ("vocals", False))
        assert player.mute_states["vocals"] is False

    def test_auto_unmute_remoto_mueve_el_checkbox(self, player):
        player._handle_remote_command("set_auto_unmute", False)
        assert player.auto_unmute_enabled is False
        assert not player.auto_unmute_check.isChecked()
        player._handle_remote_command("set_auto_unmute", True)
        assert player.auto_unmute_enabled is True
        assert player.auto_unmute_check.isChecked()

    def test_argumentos_rotos_no_revientan_el_hilo_gui(self, player):
        """El servidor ya valida, pero el slot es lo último entre un comando
        y la GUI: si revienta, se cae la app entera."""
        for cmd, arg in (("set_mute", None), ("set_mute", ("x",)),
                         ("set_volume", "bass"), ("set_volume", ("bass",)),
                         ("set_master_volume", None),
                         ("set_master_volume", "30"),
                         ("set_auto_unmute", None),
                         ("set_auto_unmute", "si")):
            player._handle_remote_command(cmd, arg)

    def test_el_snapshot_refleja_lo_que_cambio(self, player):
        player._remote_bridge = RemoteBridge()
        try:
            player._handle_remote_command("set_volume", ("drums", 70))
            player._handle_remote_command("set_master_volume", 45)
            player._handle_remote_command("set_mute", ("other", True))
            player._handle_remote_command("set_auto_unmute", False)
            state = player._remote_bridge.snapshot_state()
            assert state["volumes"]["drums"] == 70
            assert state["master_volume"] == 45
            assert state["mute"]["other"] is True
            assert state["auto_unmute"] is False
        finally:
            player._remote_bridge = None
