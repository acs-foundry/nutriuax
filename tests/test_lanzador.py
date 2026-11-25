"""T30 · lanzador web: página con botón de arranque, CSRF y modos válidos (control de systemd simulado)."""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from nutriuax import lanzador


class ControlFalso:
    def __init__(self):
        self.modo = None
        self.llamadas = []

    def estado(self):
        return {"activo": self.modo is not None, "modo": self.modo}

    def arrancar(self, modo):
        self.llamadas.append(("arrancar", modo))
        self.modo = modo

    def parar(self):
        self.llamadas.append(("parar",))
        self.modo = None


class SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@pytest.fixture
def servidor():
    ctl = ControlFalso()
    srv = lanzador.crear_servidor(0, ctl, lista=lambda: ctl.modo is not None)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ctl
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode()


def post(url, datos):
    abridor = urllib.request.build_opener(SinRedirecciones)
    req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode(), method="POST")
    try:
        with abridor.open(req, timeout=5) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def token(html):
    return re.search(r'name="token" value="([^"]+)"', html).group(1)


def test_al_abrir_hay_boton_de_arrancar(servidor):
    url, _ = servidor
    codigo, html = get(url + "/")
    assert codigo == 200 and "Parado" in html and ">Arrancar</button>" in html
    assert all(f'value="{m}"' in html for m in lanzador.MODOS)


def test_arrancar_y_parar(servidor):
    url, ctl = servidor
    t = token(get(url + "/")[1])
    codigo, cab = post(url + "/arrancar", {"token": t, "modo": "hogar"})
    assert codigo == 303 and cab["Location"] == "/?abrir=1" and ctl.modo == "hogar"
    estado = json.loads(get(url + "/estado")[1])
    assert estado == {"activo": True, "modo": "hogar", "lista": True}
    html = get(url + "/")[1]
    assert "En marcha" in html and "Abrir NutriUAX" in html and ">Parar</button>" in html
    assert post(url + "/parar", {"token": t})[0] == 303 and ctl.modo is None


def test_sin_token_o_modo_raro_no_hace_nada(servidor):
    url, ctl = servidor
    assert post(url + "/arrancar", {"token": "falso", "modo": "estudio"})[0] == 403
    t = token(get(url + "/")[1])
    assert post(url + "/arrancar", {"token": t, "modo": "rm -rf"})[0] == 400
    assert ctl.llamadas == []
