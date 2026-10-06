"""AVM: cuándo se usa Firecrawl, que el log salga siempre y el resumen de
fuentes que ve la persona."""
from __future__ import annotations

import asyncio
import contextlib
import io
import unittest
from unittest import mock

import routers.avm_websearch as A


class _Resp:
    def __init__(self, status, text="", ctype="text/html"):
        self.status_code, self.text, self.headers = status, text, {"content-type": ctype}


def correr(candidatos, directo, firecrawl, llave="fc-test"):
    async def fake_fetch(url, **kw):
        r = directo(url)
        if isinstance(r, Exception):
            raise r
        return r

    async def fake_fc(url):
        return firecrawl(url)

    async def nada(*a, **k):
        return None

    salida = io.StringIO()
    resumen = {}
    with mock.patch.object(A, "FIRECRAWL_API_KEY", llave), \
         mock.patch.object(A, "fetch_public_http_result", fake_fetch), \
         mock.patch.object(A, "_firecrawl_scrape", fake_fc), \
         mock.patch.object(A, "_avm_cache_lookup", nada), \
         mock.patch.object(A, "_avm_cache_store", nada), \
         contextlib.redirect_stdout(salida):
        paginas = asyncio.run(A._fetch_candidate_pages(candidatos, resumen=resumen))
    return paginas, resumen, salida.getvalue()


HTML_OK = "<html><body>" + "Casa en venta 3 recámaras $4,500,000 " * 20 + "</body></html>"


class FirecrawlTests(unittest.TestCase):
    def test_portal_protegido_va_por_firecrawl(self):
        pags, res, log = correr([{"url": "https://www.inmuebles24.com/propiedades/casa-1.html"}],
                                lambda u: _Resp(200, HTML_OK),
                                lambda u: {"ok": True, "page_text": "Casa $4,500,000", "credits": 1})
        self.assertEqual(pags[0]["fetch_status"], "ok_firecrawl")
        self.assertEqual((res["leidas"], res["intentos"], res["conteo"]["leído con Firecrawl"]), (1, 1, 1))
        self.assertIn("[firecrawl] calls=1 intentos=1", log)

    def test_conexion_cortada_reintenta_con_firecrawl(self):
        pags, res, log = correr([{"url": "https://casas.ejemplo.mx/casa"}],
                                lambda u: TimeoutError("timed out"),
                                lambda u: {"ok": True, "page_text": "Casa", "credits": 1})
        self.assertEqual(pags[0]["fetch_status"], "ok_firecrawl_retry_sin_respuesta")

    def test_log_sale_aunque_firecrawl_falle(self):
        pags, res, log = correr([{"url": "https://www.lamudi.com.mx/x"}],
                                lambda u: _Resp(403),
                                lambda u: {"ok": False, "error": "http_402", "credits": 0})
        self.assertEqual(A.estado_lectura_simple(pags[0]["fetch_status"]), "bloqueado")
        self.assertIn("calls=0 intentos=1", log)
        self.assertIn("http_402×1", log)
        self.assertEqual(res["errores"], {"http_402": 1})

    def test_log_dice_por_que_no_se_uso(self):
        _, res, log = correr([{"url": "https://blog.ejemplo.mx/nota"}], lambda u: _Resp(200, HTML_OK),
                             lambda u: self.fail("no debía llamar a Firecrawl"))
        self.assertIn("no se usó porque ninguna página era de un portal protegido", log)
        self.assertEqual(res["conteo"]["leído"], 1)
        _, res, log = correr([{"url": "https://www.lamudi.com.mx/x"}], lambda u: _Resp(403),
                             lambda u: self.fail("sin llave no hay Firecrawl"), llave="")
        self.assertIn("falta FIRECRAWL_API_KEY", log)
        self.assertFalse(res["activo"])

    def test_estado_al_arrancar(self):
        with mock.patch.object(A, "FIRECRAWL_API_KEY", "x"):
            self.assertEqual(A.estado_firecrawl(), "activo")
        with mock.patch.object(A, "FIRECRAWL_API_KEY", ""):
            self.assertEqual(A.estado_firecrawl(), "inactivo: falta FIRECRAWL_API_KEY")


if __name__ == "__main__":
    unittest.main()
