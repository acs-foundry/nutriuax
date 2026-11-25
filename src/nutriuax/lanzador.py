"""Lanzador web local de NutriUAX (T30): http://127.0.0.1:8771 con botones para arrancar y parar la app.

Servicio ligero y siempre encendido (solo biblioteca estándar; no carga pandas ni el solver). La app Streamlit
corre como servicio de usuario `nutriuax-app@<modo>` (estudio | consulta | hogar) y solo cuando se arranca desde
aquí; al estar lista, la página abre http://127.0.0.1:8501.

    python -m nutriuax.lanzador            # o el servicio deploy/nutriuax-lanzador.service
"""
from __future__ import annotations

import html
import json
import secrets
import socket
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = 8771
PUERTO_APP = 8501
MAX_POST_BYTES = 65536
MODOS = {"estudio": "Estudio clínico", "consulta": "Consulta de dietista", "hogar": "Menú familiar (hogar)"}
SERVICIO = "nutriuax-app@{modo}"


class ControlSystemd:
    """Arranca y para `nutriuax-app@<modo>` con systemctl --user (un solo modo a la vez)."""

    def _systemctl(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["systemctl", "--user", *args], check=False, capture_output=True, text=True, timeout=20)

    def estado(self) -> dict:
        for modo in MODOS:
            if self._systemctl("is-active", SERVICIO.format(modo=modo)).stdout.strip() in ("active", "activating"):
                return {"activo": True, "modo": modo}
        return {"activo": False, "modo": None}

    def arrancar(self, modo: str) -> None:
        self.parar()
        self._systemctl("start", SERVICIO.format(modo=modo))

    def parar(self) -> None:
        for modo in MODOS:
            self._systemctl("stop", SERVICIO.format(modo=modo))


def app_lista(puerto: int = PUERTO_APP) -> bool:
    """¿Responde ya la app en localhost:puerto?"""
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.5):
            return True
    except OSError:
        return False


def pagina(estado: dict, token: str, url_app: str) -> str:
    activo, modo = estado["activo"], estado["modo"]
    url_segura = html.escape(url_app, quote=True)
    url_js = json.dumps(url_app)
    token_seguro = html.escape(token, quote=True)
    opciones = "".join(f'<option value="{k}"{" selected" if k == (modo or "consulta") else ""}>{html.escape(v)}</option>'
                       for k, v in MODOS.items())
    if activo:
        estado_html = (f'<p class="ok">● En marcha · {html.escape(MODOS[modo])}</p>'
                       f'<p><a class="boton" href="{url_segura}" target="_self">Abrir NutriUAX</a></p>')
    else:
        estado_html = '<p class="off">○ Parado</p>'
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>NutriUAX · lanzador</title>
<style>
 body {{ font-family: system-ui, sans-serif; background: #F5FAF8; color: #1E293B; margin: 0; }}
 main {{ max-width: 520px; margin: 10vh auto; background: #fff; border: 1px solid #E2E8F0; border-radius: 16px;
        padding: 28px 32px; box-shadow: 0 6px 18px rgba(15,107,94,.10); }}
 h1 {{ margin: 0 0 4px; font-size: 1.6rem; }} p.sub {{ color: #5B6573; margin-top: 0; }}
 .ok {{ color: #0B7A3B; font-weight: 600; }} .off {{ color: #5B6573; font-weight: 600; }}
 button, .boton {{ background: #0F6B5E; color: #fff; border: 0; border-radius: 10px; padding: 10px 18px; font-size: 1rem;
          font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }}
 button.parar {{ background: #fff; color: #0F6B5E; border: 1px solid #0F6B5E; }}
 select {{ font-size: 1rem; padding: 8px; border-radius: 8px; border: 1px solid #E2E8F0; }}
 form {{ display: inline-block; margin: 6px 8px 6px 0; }} #espera {{ color: #5B6573; }}
</style></head><body><main>
<h1>NutriUAX</h1><p class="sub">Dietas y menús con control de Leu/Ile/Val · solo en este equipo</p>
{estado_html}
<form method="post" action="/arrancar"><input type="hidden" name="token" value="{token_seguro}">
 <select name="modo" aria-label="Modo">{opciones}</select> <button type="submit">{"Reiniciar" if activo else "Arrancar"}</button></form>
{'<form method="post" action="/parar"><input type="hidden" name="token" value="' + token_seguro + '"><button class="parar" type="submit">Parar</button></form>' if activo else ''}
<p id="espera"></p>
<script>
 // tras arrancar, espera a que la app responda y ábrela
 if (new URLSearchParams(location.search).has("abrir")) {{
   const e = document.getElementById("espera"); let n = 0;
   const t = setInterval(async () => {{
     n++; e.textContent = "Arrancando… " + n + " s";
     try {{ const r = await fetch("/estado"); const j = await r.json();
           if (j.lista) {{ clearInterval(t); location.href = {url_js}; }} }} catch (_) {{}}
     if (n > 90) {{ clearInterval(t); e.textContent = "No ha arrancado en 90 s: revisa «journalctl --user -u nutriuax-app@…»."; }}
   }}, 1000);
 }}
</script></main></body></html>"""


def crear_servidor(puerto: int = PUERTO, control=None, lista=app_lista, url_app: str = f"http://127.0.0.1:{PUERTO_APP}"
                   ) -> ThreadingHTTPServer:
    control = control or ControlSystemd()
    token = secrets.token_urlsafe(16)

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _responder(self, codigo: int, cuerpo: str = "", tipo: str = "text/html; charset=utf-8",
                       cabeceras: dict | None = None) -> None:
            datos = cuerpo.encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (cabeceras or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(datos)

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta == "/":
                return self._responder(200, pagina(control.estado(), token, url_app))
            if ruta == "/estado":
                return self._responder(200, json.dumps({**control.estado(), "lista": lista()}),
                                       "application/json; charset=utf-8")
            return self._responder(404, "No encontrado")

        def do_POST(self):
            raw_len = self.headers.get("Content-Length") or "0"
            try:
                largo = int(raw_len)
            except ValueError:
                return self._responder(400, "Content-Length inválido")
            if largo < 0:
                return self._responder(400, "Content-Length negativo")
            if largo > MAX_POST_BYTES:
                return self._responder(413, "Cuerpo demasiado grande")
            cuerpo = self.rfile.read(largo).decode("utf-8", errors="replace")
            datos = urllib.parse.parse_qs(cuerpo)
            if not secrets.compare_digest((datos.get("token") or [""])[0], token):
                return self._responder(403, "Prohibido")
            if self.path == "/arrancar":
                modo = (datos.get("modo") or ["consulta"])[0]
                if modo not in MODOS:
                    return self._responder(400, "Modo no válido")
                control.arrancar(modo)
                return self._responder(303, "", cabeceras={"Location": "/?abrir=1"})
            if self.path == "/parar":
                control.parar()
                return self._responder(303, "", cabeceras={"Location": "/"})
            return self._responder(404, "No encontrado")

    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)


def main() -> int:
    srv = crear_servidor()
    print(f"Lanzador de NutriUAX en http://127.0.0.1:{PUERTO}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
