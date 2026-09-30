"""Formulario de soporte: el mensaje llega a soporte con los datos de la
cuenta tomados de la sesión, la imagen como adjunto y reply_to al usuario."""
from __future__ import annotations

import asyncio
import base64
import io
import types
import unittest
from unittest import mock

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from routers import soporte as s


class _Resp:
    def __init__(self, code=200):
        self.status_code = code
        self.text = ""


class _Cliente:
    enviados: list = []
    codigo = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _Cliente.enviados.append(json)
        return _Resp(_Cliente.codigo)


def _imagen(datos=b"\x89PNG....", tipo="image/png"):
    return UploadFile(io.BytesIO(datos), filename="c.png", headers=Headers({"content-type": tipo}))


class SoporteMensajeTests(unittest.TestCase):
    def setUp(self):
        s._envios.clear()
        _Cliente.enviados = []
        _Cliente.codigo = 200

    def _enviar(self, mensaje="No me carga la ficha", imagen=None, cuenta=None):
        async def uid(_r, detail=""):
            return "u1"

        async def datos(_u):
            return cuenta or {"user_id": "u1", "nombre": "Ana Pérez", "email": "ana@x.com",
                              "telefono": "", "plan": "pro", "organizacion": "Casa <Uno>"}

        cfg = types.SimpleNamespace(resend_api_key="k", resend_from="Broquer <hola@broquer.app>")
        with mock.patch.object(s, "require_user_id", uid), mock.patch.object(s, "datos_de_cuenta", datos), \
             mock.patch.object(s, "settings", cfg), mock.patch.object(s.httpx, "AsyncClient", _Cliente):
            return asyncio.run(s.enviar_mensaje(object(), mensaje=mensaje, pagina="/guia-agente.html",
                                                dispositivo="Web", imagen=imagen))

    def test_envia_con_datos_de_cuenta_y_reply_to(self):
        r = self._enviar(imagen=_imagen())
        self.assertEqual(r, {"ok": True, "email": "ana@x.com"})
        p = _Cliente.enviados[0]
        self.assertEqual(p["to"], [s.SOPORTE_EMAIL])
        self.assertEqual(p["reply_to"], "ana@x.com")
        self.assertIn("Ana Pérez", p["subject"])
        self.assertIn("No me carga la ficha", p["html"])
        self.assertIn("Casa &lt;Uno&gt;", p["html"])
        self.assertEqual(base64.b64decode(p["attachments"][0]["content"]), b"\x89PNG....")
        self.assertEqual(p["attachments"][0]["filename"], "captura.png")

    def test_sin_imagen_no_manda_adjuntos(self):
        self._enviar()
        self.assertNotIn("attachments", _Cliente.enviados[0])

    def test_valida_mensaje_e_imagen(self):
        for kwargs, codigo in (({"mensaje": "  "}, 422),
                               ({"imagen": _imagen(tipo="application/pdf")}, 422),
                               ({"imagen": _imagen(b"x" * (s.MAX_IMAGEN + 1))}, 413)):
            with self.assertRaises(HTTPException) as e:
                self._enviar(**kwargs)
            self.assertEqual(e.exception.status_code, codigo)
        self.assertEqual(_Cliente.enviados, [])

    def test_limite_por_hora(self):
        for _ in range(s.MAX_POR_HORA):
            self._enviar()
        with self.assertRaises(HTTPException) as e:
            self._enviar()
        self.assertEqual(e.exception.status_code, 429)

    def test_falla_de_resend_da_error_con_el_correo(self):
        _Cliente.codigo = 500
        with self.assertRaises(HTTPException) as e:
            self._enviar()
        self.assertEqual(e.exception.status_code, 502)
        self.assertIn(s.SOPORTE_EMAIL, e.exception.detail)

    def test_datos_de_cuenta(self):
        async def get(tabla, params, timeout=None):
            return {"usuarios": [{"email": "ana@x.com", "plan": "pro"}],
                    "perfiles": [{"nombre": "Ana", "telefono": "555"}],
                    "organizaciones": [{"nombre": "Casa Uno"}]}[tabla]

        async def org(_u):
            return "o1"

        with mock.patch.object(s, "get_rows", get), mock.patch.object(s, "get_org_id_for_user", org):
            d = asyncio.run(s.datos_de_cuenta("u1"))
        self.assertEqual(d, {"user_id": "u1", "nombre": "Ana", "email": "ana@x.com", "telefono": "555",
                             "plan": "pro", "organizacion": "Casa Uno"})


if __name__ == "__main__":
    unittest.main()
