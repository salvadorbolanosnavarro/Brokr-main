"""Sitio web público (routers/sitios.py): páginas SSR, filtros, datos privados
que nunca salen, formulario → Buzón y dominio propio → slug."""
from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.sitios as S

ORG = "11111111-1111-1111-1111-111111111111"
P1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
P2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class SitioPublicoTests(unittest.TestCase):
    def setUp(self):
        self.sitio = {"id": "s1", "slug": "navarro", "org_id": ORG, "tipo": "organizacion", "user_id": None, "activo": True,
                      "nombre": "Grupo Prueba", "eslogan": "Tu casa", "color_primario": "#0b2545", "color_secundario": "#13a89e",
                      "mostrar_asesor": True, "incluir_bolsa": False, "traductor": True, "ga4_id": "G-ABC123",
                      "meta_pixel_id": "123", "dominio": "www.prueba.mx", "dominio_estado": "activo", "redes": {}}
        self.db = {
            "sitios": [self.sitio],
            "propiedades": [
                {"id": P1, "org_id": ORG, "estatus": "activa", "titulo": "Casa en Altozano", "tipo": "casa", "ciudad": "Morelia",
                 "colonia": "Altozano", "recamaras": 3, "banos": 2, "fotos": ["https://x/f1.jpg"], "calle": "Secreta 123",
                 "notas": "NOTA INTERNA", "codigo_llave": "LLAVE-9", "descripcion_privada": "PRIVADA",
                 "operaciones": [{"tipo": "venta", "precio": 4500000, "moneda": "MXN"}], "caracteristicas": ["alberca"]},
                {"id": P2, "org_id": ORG, "estatus": "activa", "titulo": "Depa centro", "tipo": "departamento", "ciudad": "Morelia",
                 "operaciones": [{"tipo": "renta", "precio": 12000, "moneda": "MXN"}]},
            ],
            "sitio_paginas": [{"id": "pg1", "sitio_id": "s1", "titulo": "Vende con nosotros", "slug": "vende",
                               "contenido_html": "<p>Te ayudamos</p>", "publicada": True, "en_menu": True, "meta_titulo": "Vende tu casa"}],
            "organizacion_miembros": [{"user_id": "u-owner", "org_id": ORG}],
            "usuarios": [],
        }
        self.leads = []

        async def get_rows(t, params, timeout=None):
            filas = [dict(x) for x in self.db.get(t, [])]
            if t == "sitios" and "dominio" in params:
                v = params["dominio"].split(".", 1)[1].lower()
                return [x for x in filas if (x.get("dominio") or "").lower() == v]
            if t == "propiedades" and "id" in params:
                return [x for x in filas if x["id"] == params["id"][3:]]
            return filas

        async def registrar_lead(**kw):
            self.leads.append(kw)
            return {"ok": True}

        S._CACHE_DOM.clear()
        S._RL.clear()
        self.parches = [mock.patch.object(S, "get_rows", get_rows), mock.patch("core.buzon.registrar_lead", registrar_lead)]
        for p in self.parches:
            p.start()
        app = FastAPI()
        app.include_router(S.router)
        S.instalar_middleware(app)
        self.c = TestClient(app)

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_inicio_con_open_graph_seo_y_analitica(self):
        r = self.c.get("/s/navarro")
        self.assertEqual(r.status_code, 200)
        h = r.text
        for t in ('property="og:title"', 'property="og:image"', "G-ABC123", "fbq(", "Casa en Altozano", "Depa centro",
                  'rel="canonical"', "https://www.prueba.mx", "Vende con nosotros", 'name="viewport"'):
            self.assertIn(t, h)

    def test_nunca_salen_datos_privados(self):
        for ruta in ("/s/navarro", f"/s/navarro/inmueble/{P1}", f"/p/{P1}"):
            h = self.c.get(ruta).text
            for secreto in ("Secreta 123", "NOTA INTERNA", "LLAVE-9", "PRIVADA"):
                self.assertNotIn(secreto, h, f"{secreto} en {ruta}")

    def test_venta_renta_y_buscador(self):
        self.assertIn("Casa en Altozano", self.c.get("/s/navarro/venta").text)
        self.assertNotIn("Depa centro", self.c.get("/s/navarro/venta").text)
        self.assertIn("Depa centro", self.c.get("/s/navarro/renta").text)
        h = self.c.get("/s/navarro/buscar?operacion=venta&rec=3&car=alberca").text
        self.assertIn("1 resultado", h)
        self.assertIn("0 resultado", self.c.get("/s/navarro/buscar?pmax=1000000&operacion=venta").text)

    def test_ficha_con_formulario_y_json_ld(self):
        h = self.c.get(f"/s/navarro/inmueble/{P1}").text
        self.assertIn("RealEstateListing", h)
        self.assertIn('name="propiedad_id"', h)
        self.assertEqual(self.c.get("/s/navarro/inmueble/no-existe").status_code, 404)

    def test_pagina_propia_sitemap_robots(self):
        h = self.c.get("/s/navarro/p/vende").text
        self.assertIn("Te ayudamos", h)
        self.assertIn("<title>Vende tu casa</title>", h)
        sm = self.c.get("/s/navarro/sitemap.xml").text
        self.assertIn(f"https://www.prueba.mx/inmueble/{P1}", sm)
        self.assertIn("https://www.prueba.mx/p/vende", sm)
        self.assertIn("Sitemap: https://www.prueba.mx/sitemap.xml", self.c.get("/s/navarro/robots.txt").text)

    def test_formulario_llega_al_buzon(self):
        r = self.c.post("/s/navarro/contacto", data={"nombre": "Ana", "telefono": "4431234567", "mensaje": "Me interesa",
                                                     "propiedad_id": P1}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn(f"/inmueble/{P1}?enviado=1", r.headers["location"])
        self.assertEqual(len(self.leads), 1)
        L = self.leads[0]
        self.assertEqual((L["canal"], L["fuente"], L["propiedad_id"], L["org_id"]), ("sitio", "www.prueba.mx", P1, ORG))
        # trampa para bots: no registra
        self.c.post("/s/navarro/contacto", data={"nombre": "Bot", "telefono": "1", "sitio_web": "spam"}, follow_redirects=False)
        self.assertEqual(len(self.leads), 1)
        self.assertEqual(self.c.post("/s/navarro/contacto", data={"nombre": "Sin datos"}).status_code, 400)

    def test_dominio_propio_se_traduce_al_sitio(self):
        r = self.c.get("/venta", headers={"host": "www.prueba.mx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Casa en Altozano", r.text)
        self.assertIn('href="/inmueble/', r.text)          # ligas sin /s/slug
        # Host de Broquer no se toca
        self.assertEqual(self.c.get("/venta").status_code, 404)

    def test_sitio_inactivo_404(self):
        self.db["sitios"] = []
        self.assertEqual(self.c.get("/s/navarro").status_code, 404)


class InstruccionesDnsTests(unittest.TestCase):
    def test_raiz_y_subdominio(self):
        self.assertEqual([x["nombre"] for x in S.instrucciones_dns("prueba.mx")], ["@", "www"])
        self.assertEqual(S.instrucciones_dns("www.prueba.mx")[0]["nombre"], "www")


if __name__ == "__main__":
    unittest.main()
