"""CORS: observar (default) acepta todo y anota; estricto solo la lista."""
import logging
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.cors as cors


def _app(modo, extra=""):
    app = FastAPI()

    @app.get("/x")
    def x():
        return {"ok": True}

    original_modo, original_extra = cors.settings.cors_modo, cors.settings.cors_origenes_extra
    object.__setattr__(cors.settings, "cors_modo", modo)
    object.__setattr__(cors.settings, "cors_origenes_extra", extra)
    try:
        cors.instalar_cors(app)
    finally:
        object.__setattr__(cors.settings, "cors_modo", original_modo)
        object.__setattr__(cors.settings, "cors_origenes_extra", original_extra)
    return TestClient(app)


def _preflight(client, origen):
    return client.options("/x", headers={"Origin": origen, "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": "authorization,content-type"})


class CorsTests(unittest.TestCase):
    def test_lista_incluye_web_staging_ios_y_antiguos(self):
        lista = cors.origenes_permitidos("")
        for o in ("https://broquer.app", "https://www.broquer.app", "https://staging.broquer.app",
                  "capacitor://localhost", "https://localhost", "ionic://localhost",
                  "https://navarroai.github.io", "https://app.navarroai.com.mx"):
            self.assertIn(o, lista)

    def test_extra_se_suma_sin_duplicar(self):
        lista = cors.origenes_permitidos(" https://Otro.mx/ , https://broquer.app")
        self.assertIn("https://otro.mx", lista)
        self.assertEqual(lista.count("https://broquer.app"), 1)

    def test_default_sin_variable_es_observar(self):
        self.assertFalse(cors.modo_estricto(""))
        self.assertFalse(cors.modo_estricto("observar"))
        self.assertFalse(cors.modo_estricto("cualquier-cosa"))
        self.assertTrue(cors.modo_estricto(" Estricto "))

    def test_observar_acepta_todo_y_anota_desconocidos_una_vez(self):
        c = _app("observar")
        with self.assertLogs("broquer.cors", level=logging.WARNING) as cap:
            for _ in range(3):
                r = _preflight(c, "https://desconocido.example")
                self.assertEqual(r.status_code, 200)
            r = c.get("/x", headers={"Origin": "https://broquer.app"})
            self.assertEqual(r.headers.get("access-control-allow-origin"), "*")
        anotados = [m for m in cap.output if "desconocido.example" in m]
        self.assertEqual(len(anotados), 1)
        self.assertFalse(any("https://broquer.app " in m for m in cap.output))

    def test_estricto_solo_lista(self):
        c = _app("estricto", extra="https://extra.mx")
        for o in ("https://broquer.app", "capacitor://localhost", "https://staging.broquer.app", "https://extra.mx"):
            r = _preflight(c, o)
            self.assertEqual(r.status_code, 200, o)
            self.assertEqual(r.headers.get("access-control-allow-origin"), o)
        r = _preflight(c, "https://malo.example")
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(c.get("/x", headers={"Origin": "https://malo.example"}).headers.get("access-control-allow-origin"))

    def test_servidores_sin_origin_no_se_afectan(self):
        c = _app("estricto")
        r = c.get("/x")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
