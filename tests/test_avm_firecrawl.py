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


# ── Formato de lo que se manda a Firecrawl (API v2) ──────────────────────────
# Reglas tomadas de docs.firecrawl.dev/api-reference/endpoint/scrape y /search.
import re as _re  # noqa: E402

V2_SCRAPE_CAMPOS = {"url", "formats", "onlyMainContent", "includeTags", "excludeTags", "maxAge", "headers", "waitFor",
                    "mobile", "skipTlsVerification", "timeout", "parsers", "actions", "location", "removeBase64Images",
                    "blockAds", "proxy", "storeInCache", "zeroDataRetention"}
V2_FORMATOS = {"markdown", "summary", "html", "rawHtml", "links", "images", "screenshot", "json", "changeTracking", "branding"}
V2_SEARCH_CAMPOS = {"query", "limit", "sources", "categories", "tbs", "location", "country", "timeout", "ignoreInvalidURLs", "scrapeOptions"}


def validar_scrape_v2(p):
    errores = []
    for k in p:
        if k not in V2_SCRAPE_CAMPOS:
            errores.append(f"campo desconocido {k}")
    if not isinstance(p.get("url"), str) or not p["url"].startswith("http"):
        errores.append("url")
    for f in p.get("formats", []):
        tipo = f if isinstance(f, str) else (f.get("type") if isinstance(f, dict) else None)
        if tipo not in V2_FORMATOS:
            errores.append(f"formato {f!r}")
        if tipo == "json" and isinstance(f, dict) and not (f.get("schema") or f.get("prompt")):
            errores.append("json sin schema ni prompt")
        if tipo == "json" and isinstance(f, str):
            errores.append("json como texto necesita objeto con schema/prompt en v2")
    if "jsonOptions" in p:
        errores.append("jsonOptions es de v1")
    if p.get("proxy") not in (None, "basic", "enhanced", "auto"):
        errores.append("proxy")
    t = p.get("timeout")
    if t is not None and not (isinstance(t, int) and 1000 <= t <= 300000):
        errores.append("timeout fuera de 1000-300000 ms")
    loc = p.get("location")
    if loc is not None and not _re.fullmatch(r"[A-Z]{2}", str(loc.get("country", ""))):
        errores.append("location.country debe ser ISO de 2 letras mayúsculas")
    return errores


class PayloadFirecrawlTests(unittest.TestCase):
    def test_endpoints_son_v2(self):
        self.assertTrue(A.FIRECRAWL_SCRAPE_URL.endswith("/v2/scrape"))
        self.assertTrue(A.FIRECRAWL_SEARCH_URL.endswith("/v2/search"))

    def test_scrape_cumple_v2_con_y_sin_extraccion(self):
        for extraer in (True, False):
            with mock.patch.object(A, "FIRECRAWL_STRUCTURED_EXTRACT", extraer):
                p = A.firecrawl_scrape_payload("https://www.inmuebles24.com/x.html")
            self.assertEqual(validar_scrape_v2(p), [], p)
            tipos = [f["type"] for f in p["formats"]]
            self.assertEqual(tipos, ["markdown", "json"] if extraer else ["markdown"])

    def test_lo_que_se_mandaba_antes_era_invalido_en_v1(self):
        # Antes: POST /v1/scrape con un objeto {"type": "json"} en "formats".
        # En v1 "formats" sólo acepta textos (y la extracción va en
        # "jsonOptions"): por eso Firecrawl respondía 400 a todas las páginas.
        viejo = {"url": "https://x.mx", "formats": ["markdown", {"type": "json", "prompt": "p", "schema": {}}],
                 "proxy": "auto", "onlyMainContent": True, "timeout": 45000}
        v1_formatos_validos = all(isinstance(f, str) for f in viejo["formats"])
        self.assertFalse(v1_formatos_validos)
        self.assertNotIn("/v1/", A.FIRECRAWL_SCRAPE_URL)

    def test_timeout_siempre_en_rango(self):
        for seg in (0.1, 45, 9999):
            with mock.patch.object(A, "FIRECRAWL_TIMEOUT", seg):
                self.assertEqual(validar_scrape_v2(A.firecrawl_scrape_payload("https://x.mx")), [])

    def test_search_cumple_v2(self):
        p = A.firecrawl_search_payload("casa en venta Jesús del Monte Morelia " * 30)
        self.assertTrue(set(p) <= V2_SEARCH_CAMPOS, p)
        self.assertNotIn("lang", p)
        self.assertRegex(p["country"], r"^[A-Z]{2}$")
        self.assertLessEqual(len(p["query"]), 500)
        self.assertTrue(1 <= p["limit"] <= 100)

    def test_resultados_v1_y_v2(self):
        item = {"url": "https://a.mx", "title": "t", "description": "d"}
        self.assertEqual(A.firecrawl_resultados_web({"web": [item], "news": []}), [item])
        self.assertEqual(A.firecrawl_resultados_web([item]), [item])
        self.assertEqual(A.firecrawl_resultados_web(None), [])

    def test_error_se_loguea_con_motivo_y_sin_llave(self):
        resp = mock.Mock(status_code=400, text='{"success":false,"error":"Bad Request: unrecognized key fc-secreta ' + "x" * 500 + '"}')
        salida = io.StringIO()
        with mock.patch.object(A, "FIRECRAWL_API_KEY", "fc-secreta"), contextlib.redirect_stdout(salida):
            A._log_error_firecrawl("scrape", "https://www.lamudi.com.mx/x", resp)
        linea = salida.getvalue()
        self.assertIn("[firecrawl] error scrape http_400", linea)
        self.assertIn("unrecognized key", linea)
        self.assertNotIn("fc-secreta", linea)
        self.assertLess(len(linea), 500)


if __name__ == "__main__":
    unittest.main()
