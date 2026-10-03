"""Arnés de pruebas de navegador para Broquer (sin Supabase ni backend reales).

Sirve el repo en un puerto local, abre Chromium (Playwright) y responde las
llamadas a Supabase REST/Auth y a api.broquer.app con una base en memoria.
No se corre en CI (no es test_*.py); se usa a mano:

    python scripts/e2e/e2e_propiedades.py
"""
from __future__ import annotations

import base64
import functools
import http.server
import json
import re
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_ID = "10000000-0000-0000-0000-000000000001"
ORG_ID = "00000000-0000-0000-0000-0000000000a1"
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=")


def fake_jwt(sub=USER_ID):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'HS256'})}.{b64({'sub': sub, 'exp': int(time.time()) + 86400, 'role': 'authenticated'})}.firma"


class FakeDB:
    def __init__(self, tablas=None):
        self.t = {k: list(v) for k, v in (tablas or {}).items()}
        self.log = []

    def _match(self, fila, params):
        for k, v in params.items():
            if k in ("select", "order", "limit", "offset", "or", "and", "on_conflict", "columns"):
                continue
            op, _, val = v.partition(".")
            cur = fila.get(k)
            if op == "eq" and str(cur) != val and not (val in ("true", "false") and str(cur).lower() == val):
                return False
            if op == "neq" and str(cur) == val:
                return False
            if op == "in":
                vals = [x.strip('"') for x in val.strip("()").split(",")]
                if str(cur) not in vals:
                    return False
            if op == "is" and val == "null" and cur is not None:
                return False
            if op == "not" and val.startswith("is.null") and cur is None:
                return False
        return True

    def handle(self, method, tabla, params, body):
        self.log.append((method, tabla, params, body))
        filas = self.t.setdefault(tabla, [])
        if method == "GET":
            out = [f for f in filas if self._match(f, params)]
            if "limit" in params:
                out = out[: int(params["limit"])]
            return out
        if method == "POST":
            nuevos = body if isinstance(body, list) else [body]
            for n in nuevos:
                n = dict(n)
                n.setdefault("id", str(uuid.uuid4()))
                n.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
                filas.append(n)
            return nuevos
        if method == "PATCH":
            out = []
            for f in filas:
                if self._match(f, params):
                    f.update(body or {})
                    out.append(f)
            return out
        if method == "DELETE":
            quedan = [f for f in filas if not self._match(f, params)]
            borradas = [f for f in filas if self._match(f, params)]
            self.t[tabla] = quedan
            return borradas
        return []


_CDN_CACHE: dict = {}


def _cdn(url):
    """Baja librerías de CDN con urllib (respeta el proxy del entorno)."""
    if url not in _CDN_CACHE:
        import ssl
        import urllib.request
        ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt") if Path("/root/.ccr/ca-bundle.crt").exists() else None
        with urllib.request.urlopen(url, timeout=30, context=ctx) as r:
            _CDN_CACHE[url] = (r.read(), r.headers.get("content-type", "application/javascript"))
    body, ctype = _CDN_CACHE[url]
    return {"status": 200, "headers": {"content-type": ctype, "access-control-allow-origin": "*"}, "body": body}


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass


def servir_repo():
    handler = functools.partial(_Silencioso, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def instalar_mocks(page, db: FakeDB, api_handler=None):
    """api_handler(method, path, query, body) -> (status, json) | None."""

    def responder(route, status=200, data=None, ctype="application/json", raw=None):
        route.fulfill(status=status, headers={"content-type": ctype, "access-control-allow-origin": "*"},
                      body=raw if raw is not None else json.dumps(data if data is not None else []))

    def on_route(route):
        req = route.request
        url = urllib.parse.urlparse(req.url)
        host = url.netloc
        if host.startswith("127.0.0.1"):
            return route.continue_()
        body = None
        if req.post_data:
            try:
                body = json.loads(req.post_data)
            except Exception:
                body = req.post_data
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers={"access-control-allow-origin": "*",
                                                      "access-control-allow-headers": "*",
                                                      "access-control-allow-methods": "*"})
        if "supabase.co" in host:
            if url.path.startswith("/auth/v1/user"):
                return responder(route, data={"id": USER_ID, "email": "chava@prueba.mx"})
            m = re.match(r"/rest/v1/([a-z_0-9]+)", url.path)
            if m:
                params = dict(urllib.parse.parse_qsl(url.query))
                return responder(route, data=db.handle(req.method, m.group(1), params, body))
            if url.path.startswith("/storage/"):
                return responder(route, data={"Key": "x"})
            return responder(route, data={})
        if "api.broquer.app" in host:
            q = dict(urllib.parse.parse_qsl(url.query))
            if api_handler:
                r = api_handler(req.method, url.path, q, body)
                if r is not None:
                    return responder(route, status=r[0], data=r[1])
            if url.path == "/org":
                return responder(route, data={"tiene_org": True, "org_id": ORG_ID, "es_empresa": True,
                                              "es_admin": True, "rol_org": "owner",
                                              "permisos": {"exportar": True, "ver_comisiones": True}})
            if url.path == "/org/miembros":
                return responder(route, data={"miembros": [
                    {"user_id": USER_ID, "nombre": "Chava", "activo": True, "rol_org": "owner"},
                    {"user_id": "10000000-0000-0000-0000-000000000002", "nombre": "Agente Uno", "activo": True}],
                    "es_admin": True})
            return responder(route, data={})
        if "tile.openstreetmap.org" in host:
            return responder(route, ctype="image/png", raw=PNG_1PX)
        if "cdnjs.cloudflare.com" in host or "cdn.jsdelivr.net" in host or "unpkg.com" in host:
            return route.fulfill(**_cdn(req.url))
        return route.abort()

    page.route("**/*", on_route)


def nueva_pagina(browser, base, ancho=375, alto=812):
    ctx = browser.new_context(viewport={"width": ancho, "height": alto}, has_touch=True, is_mobile=ancho < 700,
                              device_scale_factor=2)
    ctx.add_init_script(f"""
      try {{ if (location.hostname !== '127.0.0.1') throw 0;
      localStorage.setItem('sb_token', '{fake_jwt()}');
      localStorage.setItem('sb_user', JSON.stringify({{id: '{USER_ID}', email: 'chava@prueba.mx'}}));
      localStorage.setItem('sesion_activa', '1'); }} catch (e) {{}}
    """)
    page = ctx.new_page()
    errores = []
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.on("console", lambda m: errores.append("console: " + m.text) if m.type == "error" else None)
    return page, errores
