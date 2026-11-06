"""AVM: páginas de listado rinden un comparable por anuncio, búsquedas más
amplias y nada de ligas ni frases internas en lo que ve la persona.

Caso real que motivó esto: Firecrawl leyó 14 páginas sin errores y la
estimación salió con solo 2 comparables."""
from __future__ import annotations

import asyncio
import contextlib
import io
import unittest
from unittest import mock

import routers.avm_websearch as A
from core import avm_fuentes as F


LISTADO = {
    "anuncios": [
        {"titulo": "Local en renta García de León", "ubicacion": "Nueva Chapultepec",
         "operacion": "renta", "precio": 45000, "moneda": "MXN", "m2_construccion": 250,
         "url": "/propiedades/local-garcia-leon-123.html"},
        {"titulo": "Local planta alta", "ubicacion": "Chapultepec Sur", "precio": 30000,
         "m2_construccion": 180, "url": "https://www.inmuebles24.com/propiedades/local-456.html"},
        {"titulo": "Sin precio", "m2_construccion": 100},
    ]
}


class ExtraccionEstructuradaTests(unittest.TestCase):
    def test_schema_pide_lista_de_anuncios(self):
        props = A._FIRECRAWL_LISTING_SCHEMA["properties"]
        self.assertEqual(props["anuncios"]["type"], "array")
        self.assertIn("url", props["anuncios"]["items"]["properties"])

    def test_un_anuncio_por_linea_con_liga_absoluta(self):
        bloque = A._formatea_estructurado_firecrawl(LISTADO, "https://www.inmuebles24.com/locales-en-renta.html")
        self.assertTrue(bloque.startswith(A.MARCA_ANUNCIOS))
        self.assertIn("2 anuncios", bloque)
        self.assertIn("1) Local en renta García de León", bloque)
        self.assertIn("url=https://www.inmuebles24.com/propiedades/local-garcia-leon-123.html", bloque)
        self.assertIn("2) Local planta alta", bloque)
        self.assertNotIn("Sin precio", bloque)
        self.assertNotIn("FIRECRAWL", bloque.upper())

    def test_formato_anterior_sigue_funcionando(self):
        bloque = A._formatea_estructurado_firecrawl({"precio": 4500000, "m2_construccion": 200})
        self.assertIn("1) precio=4500000", bloque)
        self.assertEqual(A._formatea_estructurado_firecrawl({}), "")
        self.assertEqual(A._formatea_estructurado_firecrawl({"anuncios": []}), "")

    def test_bloque_respeta_su_presupuesto(self):
        muchos = {"anuncios": [{"titulo": "x" * 130, "precio": 1000 + i, "m2_construccion": 100}
                               for i in range(200)]}
        bloque = A._formatea_estructurado_firecrawl(muchos)
        self.assertLessEqual(len(bloque), A.MAX_STRUCT_CHARS + 200)
        # encabezado + una línea por anuncio + línea en blanco final
        self.assertLessEqual(bloque.count("\n") - 2, A.MAX_ANUNCIOS_POR_PAGINA)

    def test_scrape_no_recorta_el_bloque_con_el_markdown(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = {"success": True, "data": {
            "markdown": "m" * (A.MAX_TEXT_CHARS_PER_URL * 2), "json": LISTADO, "metadata": {"creditsUsed": 5}}}
        cliente = mock.AsyncMock()
        cliente.post.return_value = respuesta
        cliente.__aenter__.return_value = cliente
        with mock.patch.object(A, "FIRECRAWL_API_KEY", "fc"), \
             mock.patch.object(A.httpx, "AsyncClient", return_value=cliente):
            r = asyncio.run(A._firecrawl_scrape("https://www.inmuebles24.com/locales.html"))
        self.assertTrue(r["ok"])
        self.assertTrue(r["page_text"].startswith(A.MARCA_ANUNCIOS))
        self.assertIn("m" * A.MAX_TEXT_CHARS_PER_URL, r["page_text"])
        self.assertEqual(r["credits"], 5)


class AdvertenciaListadoTests(unittest.TestCase):
    PRECIOS = " ".join(f"${n},000" for n in range(20, 30))

    def test_con_anuncios_estructurados_dice_usarlos(self):
        texto = A.MARCA_ANUNCIOS + " ...\n" + self.PRECIOS
        adv = A._advertencia_multi_listado(texto)
        self.assertIn("comparable individual", adv)

    def test_sin_estructurados_permite_tarjetas_con_m2_propios(self):
        adv = A._advertencia_multi_listado(self.PRECIOS)
        self.assertIn("comparable distinto", adv)
        self.assertEqual(A._advertencia_multi_listado("$45,000"), "")


class CacheVersionadaTests(unittest.TestCase):
    def test_lookup_ignora_filas_del_formato_viejo_y_store_guarda_v2(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = []
        cliente = mock.AsyncMock()
        cliente.get.return_value = respuesta
        cliente.__aenter__.return_value = cliente
        with mock.patch.object(A.httpx, "AsyncClient", return_value=cliente), \
             mock.patch.object(A, "rest_url", lambda t: f"https://db/{t}"), \
             mock.patch.object(A, "service_headers", lambda **k: {}):
            asyncio.run(A._avm_cache_lookup("https://www.lamudi.com.mx/x"))
            asyncio.run(A._avm_cache_store("https://www.lamudi.com.mx/x", "c", "m", "t" * 50000))
        params = cliente.get.call_args.kwargs["params"]
        self.assertEqual(params["fetch_status"], "eq.ok_firecrawl_v2")
        guardado = cliente.post.call_args.kwargs["json"]
        self.assertEqual(guardado["fetch_status"], "ok_firecrawl_v2")
        self.assertEqual(len(guardado["page_text"]), A.MAX_PAGE_TEXT_CHARS)


class BusquedasTests(unittest.TestCase):
    def req(self, **kw):
        base = dict(colonia="Nueva Chapultepec", ciudad="Morelia", estado="Michoacán",
                    tipo_inmueble="local", operacion="renta", m2_construccion=290, m2_terreno=300)
        base.update(kw)
        return A.AvmWebSearchRequest(**base)

    def test_base_sin_precio_m2_y_con_mercadolibre(self):
        qs = A._build_search_queries(self.req(), ["Chapultepec Sur"])
        self.assertEqual(qs[0], 'local comercial en renta "Nueva Chapultepec" "Morelia"')
        self.assertFalse(any("precio m2" in q for q in qs))
        self.assertTrue(any("site:inmuebles.mercadolibre.com.mx" in q for q in qs))
        self.assertIn('local comercial en renta "Morelia" 290 m2', qs)
        self.assertIn('local comercial en renta "Chapultepec Sur" "Morelia"', qs)

    def test_terreno_usa_m2_de_terreno(self):
        qs = A._build_search_queries(self.req(tipo_inmueble="terreno", operacion="venta"))
        self.assertIn('terreno en venta "Morelia" 300 m2', qs)

    def test_sin_superficie_no_hay_query_por_tamano(self):
        qs = A._build_search_queries(self.req(m2_construccion=0, m2_terreno=0))
        self.assertFalse(any(q.endswith(" m2") for q in qs))


class InmobiliariasLocalesTests(unittest.TestCase):
    def test_acepta_anuncio_de_inmobiliaria_local(self):
        self.assertTrue(A.parece_anuncio_inmobiliario({
            "url": "https://www.inmobiliariamorelia.mx/local-123",
            "title": "Local comercial en renta, Blvd. García de León",
            "snippet": "Local de 250 m2 en planta alta. Renta $48,000 mensuales."}))

    def test_rechaza_noticias_redes_y_textos_sin_datos(self):
        casos = [
            {"url": "https://www.quadratin.com.mx/x", "title": "Renta de locales sube",
             "snippet": "Locales de 100 m2 en renta por $20,000"},
            {"url": "https://www.facebook.com/marketplace/x", "title": "Local en renta",
             "snippet": "100 m2 $20,000"},
            {"url": "https://noticiasmorelia.mx/x", "title": "Venta", "snippet": "300 m2 $5,000,000"},
            {"url": "https://www.inmobiliariamorelia.mx/x", "title": "Nosotros",
             "snippet": "Somos una inmobiliaria con 20 años de experiencia"},
        ]
        for item in casos:
            self.assertFalse(A.parece_anuncio_inmobiliario(item), item["url"])


class LigasYFrasesTests(unittest.TestCase):
    PAGINAS = [
        {"url": "https://www.inmuebles24.com/locales.html", "fetch_status": "ok_firecrawl",
         "page_text": A.MARCA_ANUNCIOS + ":\n1) Local | precio=45000 | "
                      "url=https://www.inmuebles24.com/propiedades/local-123.html\n"},
        {"url": "https://www.lamudi.com.mx/locales", "fetch_status": "http_403__firecrawl_err",
         "page_text": ""},
    ]

    def test_comparables_solo_con_ligas_consultadas(self):
        res = {"comparables": [
            {"descripcion": "a", "url": "https://www.inmuebles24.com/propiedades/local-123.html"},
            {"descripcion": "b", "url": "https://www.inmuebles24.com/locales.html"},
            {"descripcion": "c", "url": "https://www.lamudi.com.mx/locales"},
            {"descripcion": "d", "url": "https://inventada.mx/anuncio"},
        ]}
        F.sanear_resultado(res, F.urls_no_consultadas(self.PAGINAS), F.urls_permitidas(self.PAGINAS))
        urls = [c["url"] for c in res["comparables"]]
        self.assertEqual(urls, ["https://www.inmuebles24.com/propiedades/local-123.html",
                                "https://www.inmuebles24.com/locales.html", "", ""])

    def test_pdf_sin_permitidas_no_cambia(self):
        res = {"comparables": [{"descripcion": "d", "url": "https://otra.mx/x"}]}
        F.sanear_resultado(res)
        self.assertEqual(res["comparables"][0]["url"], "https://otra.mx/x")

    def test_frase_real_del_pdf_se_quita(self):
        res = {"recomendaciones": [
            "Verificar directamente en portales (Inmuebles24, Lamudi, Mercado Libre) la oferta activa "
            "de locales comerciales de 200–350 m² en el corredor García de León, ya que varios portales "
            "no permitieron acceso completo durante la consulta.",
            "El acceso independiente desde la calle es un atributo diferenciador.",
        ]}
        F.sanear_resultado(res)
        self.assertEqual(res["recomendaciones"], ["El acceso independiente desde la calle es un atributo diferenciador."])

    def test_vocabulario_vial_no_se_toca(self):
        for t in ("Vialidad con acceso directo al periférico.",
                  "La zona tiene acceso limitado al transporte público.",
                  "El edificio no permite el acceso de mascotas."):
            self.assertEqual(F.limpiar_texto(t), t)

    def test_prompt_no_sugiere_hablar_de_bloqueos(self):
        with open(A.__file__, encoding="utf-8") as fh:
            fuente = fh.read()
        self.assertNotIn("bloquearon el acceso directo", fuente)


class FetchConListadoTests(unittest.TestCase):
    def test_listado_por_firecrawl_lleva_bloque_y_advertencia_adecuada(self):
        texto = (A._formatea_estructurado_firecrawl(LISTADO, "https://www.inmuebles24.com/l.html")
                 + " ".join(f"${n},000" for n in range(20, 30)))

        async def fake_fc(url):
            return {"ok": True, "page_text": texto, "credits": 5}

        async def nada(*a, **k):
            return None

        with mock.patch.object(A, "FIRECRAWL_API_KEY", "fc"), \
             mock.patch.object(A, "_firecrawl_scrape", fake_fc), \
             mock.patch.object(A, "_avm_cache_lookup", nada), \
             mock.patch.object(A, "_avm_cache_store", nada), \
             contextlib.redirect_stdout(io.StringIO()):
            paginas = asyncio.run(A._fetch_candidate_pages(
                [{"url": "https://www.inmuebles24.com/l.html", "title": "t"}]))
        self.assertEqual(paginas[0]["fetch_status"], "ok_firecrawl")
        self.assertIn("comparable individual", paginas[0]["page_text"])
        self.assertIn(A.MARCA_ANUNCIOS, paginas[0]["page_text"])


class BuscadorPropiedadesTests(unittest.TestCase):
    """El buscador reutiliza la lectura del AVM: una página con UN anuncio
    sigue dando su precio; un listado no (se va por sus enlaces)."""

    def test_precio_solo_con_anuncio_unico(self):
        import routers.buscador_propiedades as B
        uno = A._formatea_estructurado_firecrawl({"anuncios": [{"titulo": "Casa", "precio": 4500000}]})
        varios = A._formatea_estructurado_firecrawl({"anuncios": [{"precio": 1000}, {"precio": 2000}]})
        self.assertEqual(B._extraer_precio(uno + "texto"), 4500000.0)
        self.assertIsNone(B._extraer_precio(varios))
        self.assertEqual(B._extraer_precio("DATO ESTRUCTURADO FIRECRAWL (alta confianza): precio=5000."), 5000.0)


if __name__ == "__main__":
    unittest.main()
