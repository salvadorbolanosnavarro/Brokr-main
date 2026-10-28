"""Ligas temporales de adjuntos-historial: solo para quien puede ver la nota/tarea."""
import asyncio
import unittest
from pathlib import Path
from unittest import mock

import routers.adjuntos_ligas as al


ROOT = Path(__file__).resolve().parents[1]
URL = "https://urtgysmtnvoqaljuhntz.supabase.co/storage/v1/object/public/adjuntos-historial/1712345678_ab12cd.pdf"


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class _Cliente:
    """Simula PostgREST: solo 'actividades' tiene la liga visible para el usuario."""

    def __init__(self, visibles):
        self.visibles = visibles
        self.llamadas = []

    async def get(self, url, headers=None, params=None):
        self.llamadas.append((url, headers, params))
        tabla = url.rsplit("/", 1)[-1]
        hay = any(u in params["adjuntos"] for u in self.visibles.get(tabla, []))
        return _Resp(200, [{"id": 1}] if hay else [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class RutaTests(unittest.TestCase):
    def test_saca_la_ruta_de_ligas_publicas_y_firmadas(self):
        self.assertEqual(al.ruta_de_url(URL), "1712345678_ab12cd.pdf")
        firmada = URL.replace("/public/", "/sign/") + "?token=abc"
        self.assertEqual(al.ruta_de_url(firmada), "1712345678_ab12cd.pdf")

    def test_rechaza_otros_buckets_carpetas_y_trucos(self):
        for mala in (
            URL.replace("adjuntos-historial", "fotos-propiedades"),
            URL.replace("1712345678_ab12cd.pdf", "../firmas/x.pdf"),
            URL.replace("1712345678_ab12cd.pdf", "carpeta/x.pdf"),
            URL.replace("1712345678_ab12cd.pdf", ".oculto"),
            URL.replace("https://", "http://"),
            "", None, "javascript:alert(1)",
        ):
            self.assertIsNone(al.ruta_de_url(mala), mala)


class LigasTests(unittest.TestCase):
    def _correr(self, urls, visibles, token="tok-usuario"):
        cliente = _Cliente(visibles)
        firmar = mock.AsyncMock(side_effect=lambda bucket, ruta, expires_in: f"https://firmada/{bucket}/{ruta}?e={expires_in}")
        req = mock.Mock()
        req.headers = {"authorization": f"Bearer {token}"} if token else {}
        with mock.patch.object(al, "require_user_id", mock.AsyncMock(return_value="u1")), \
             mock.patch.object(al.httpx, "AsyncClient", lambda **kw: cliente), \
             mock.patch.object(al, "rest_url", lambda tabla: f"https://sb.test/rest/v1/{tabla}"), \
             mock.patch.object(al, "create_signed_object_url", firmar):
            res = asyncio.run(al.adjuntos_ligas(al.LigasReq(urls=urls), req))
        return res, cliente, firmar

    def test_firma_si_el_usuario_ve_la_nota(self):
        res, cliente, firmar = self._correr([URL], {"actividades": [URL]})
        self.assertEqual(res["ligas"][URL], "https://firmada/adjuntos-historial/1712345678_ab12cd.pdf?e=3600")
        self.assertEqual(res["segundos"], 3600)
        # La consulta va con la sesión del usuario (RLS decide), no con service_role.
        _, headers, params = cliente.llamadas[0]
        self.assertEqual(headers["Authorization"], "Bearer tok-usuario")
        self.assertEqual(params["adjuntos"], 'cs.[{"url":"%s"}]' % URL)

    def test_tambien_busca_en_tareas(self):
        res, _, _ = self._correr([URL], {"tareas": [URL]})
        self.assertTrue(res["ligas"][URL])

    def test_no_firma_si_no_la_ve(self):
        res, _, firmar = self._correr([URL], {})
        self.assertIsNone(res["ligas"][URL])
        firmar.assert_not_called()

    def test_no_firma_ligas_de_otros_buckets(self):
        otra = URL.replace("adjuntos-historial", "firmas")
        res, cliente, firmar = self._correr([otra], {"actividades": [otra]})
        self.assertIsNone(res["ligas"][otra])
        self.assertEqual(cliente.llamadas, [])
        firmar.assert_not_called()

    def test_sin_token_es_401(self):
        with self.assertRaises(al.HTTPException) as cm:
            self._correr([URL], {"actividades": [URL]}, token="")
        self.assertEqual(cm.exception.status_code, 401)

    def test_tope_y_sin_repetidos(self):
        urls = [URL.replace("ab12cd", f"x{i}") for i in range(80)] + [URL, URL]
        res, _, _ = self._correr(urls, {})
        self.assertEqual(len(res["ligas"]), al.MAX_URLS)


class FrontendTests(unittest.TestCase):
    def test_historial_adjuntos_usa_ligas_temporales(self):
        js = (ROOT / "historial-adjuntos.js").read_text(encoding="utf-8")
        self.assertIn("'/adjuntos/ligas'", js)
        self.assertIn("data-ha-url", js)
        self.assertIn("function haAttrLiga(", js)
        # Si el backend falla, se usa la liga original (bucket aún público).
        self.assertIn("_haLigaVigente(url) || url", js)

    def test_tareas_pinta_adjuntos_con_ligas_temporales(self):
        html = (ROOT / "tareas.html").read_text(encoding="utf-8")
        self.assertIn("haAttrLiga(a.url)", html)

    def test_router_registrado(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("app.include_router(adjuntos_ligas_router)", main)


if __name__ == "__main__":
    unittest.main()
