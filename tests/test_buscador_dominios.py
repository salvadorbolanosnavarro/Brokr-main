import asyncio
import unittest
from unittest import mock

import routers.avm_websearch as A
import routers.buscador_propiedades as B


class BuscadorSoloDominiosInmobiliariosTests(unittest.TestCase):
    def test_no_mete_noticias(self):
        async def buscar(client, query, pais="MX"):
            return [{"url": "https://elpais.com/economia/nota.html", "title": "t", "snippet": "s"},
                    {"url": "https://www.lamudi.com.mx/casa-1", "title": "t", "snippet": "s"}]

        vacio = mock.AsyncMock(return_value=[])
        with mock.patch.object(A, "_search_google_cse", buscar), \
             mock.patch.object(A, "_search_brave", vacio), \
             mock.patch.object(A, "_search_tavily", vacio), \
             mock.patch.object(A, "_search_serpapi", vacio), \
             mock.patch.object(A, "_search_firecrawl", vacio):
            candidatos = asyncio.run(B._recolectar_candidatos(
                {"tipo_inmueble": "casa", "operacion": "venta", "colonia": "Centro", "ciudad": "Morelia"}))
        urls = [c["url"] for c in candidatos]
        self.assertIn("https://www.lamudi.com.mx/casa-1", urls)
        self.assertFalse(any("elpais.com" in u for u in urls))


if __name__ == "__main__":
    unittest.main()
