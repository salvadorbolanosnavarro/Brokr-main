"""Opinión de valor: solo se enlistan fuentes consultadas y nada interno llega a la persona."""
import json
import re
import unittest
from pathlib import Path

from core import avm_fuentes as F


ROOT = Path(__file__).resolve().parents[1]

PAGINAS = [
    {"url": "https://www.lamudi.com.mx/casa-1", "title": "Casa en Altozano", "portal": "Lamudi", "fetch_status": "ok", "provider": "serpapi"},
    {"url": "https://www.inmuebles24.com/casa-2", "title": "Casa 2", "portal": "Inmuebles24", "fetch_status": "ok_firecrawl_retry_403", "provider": "brave"},
    {"url": "https://www.vivanuncios.com.mx/casa-3", "title": "Casa 3", "portal": "Vivanuncios", "fetch_status": "bloqueada_sin_firecrawl"},
    {"url": "https://portal.mx/casa-4", "title": "Casa 4", "portal": "", "fetch_status": "http_403__firecrawl_timeout"},
    {"url": "https://portal.mx/casa-5", "title": "Casa 5", "fetch_status": "skipped_domain"},
    {"url": "https://www.lamudi.com.mx/casa-1/", "title": "Repetida", "fetch_status": "ok"},
]


class FuentesTests(unittest.TestCase):
    def test_solo_paginas_consultadas_sin_estados_ni_proveedores(self):
        fuentes = F.fuentes_publicas(PAGINAS)
        self.assertEqual([f["url"] for f in fuentes],
                         ["https://www.lamudi.com.mx/casa-1", "https://www.inmuebles24.com/casa-2"])
        for f in fuentes:
            self.assertEqual(set(f), {"titulo", "url", "portal"})

    def test_urls_no_consultadas(self):
        ocultas = F.urls_no_consultadas(PAGINAS)
        self.assertIn("https://www.vivanuncios.com.mx/casa-3", ocultas)
        self.assertIn("https://portal.mx/casa-4", ocultas)
        self.assertNotIn("https://www.lamudi.com.mx/casa-1", ocultas)

    def test_limpiar_texto_quita_oraciones_internas(self):
        t = ("El mercado en Altozano está activo. Algunos portales bloquearon el acceso a sus anuncios. "
             "Firecrawl leyó 3 páginas. No se pudo leer Vivanuncios. La demanda es alta.")
        self.assertEqual(F.limpiar_texto(t), "El mercado en Altozano está activo. La demanda es alta.")
        self.assertEqual(F.limpiar_texto("Sin nada raro."), "Sin nada raro.")
        self.assertEqual(F.limpiar_texto(None), None)

    def test_sanear_resultado_nuevo(self):
        res = {
            "fuentes_consultadas": F.fuentes_publicas(PAGINAS),
            "comparables": [
                {"descripcion": "Casa 3 rec", "url": "https://www.vivanuncios.com.mx/casa-3", "fuente": "Vivanuncios"},
                {"descripcion": "Casa buena", "url": "https://www.lamudi.com.mx/casa-1", "fuente": "Lamudi"},
            ],
            "comparables_descartados": [{"descripcion": "x", "url": "https://portal.mx/casa-4/", "motivo": "El sitio nos bloqueó."}],
            "advertencias": "Confianza media por pocos comparables. Varios portales estaban bloqueados.",
            "recomendaciones": ["Visita la zona.", "Reintenta cuando Firecrawl tenga crédito."],
            "firecrawl": {"activo": True}, "proveedores_busqueda_configurados": {"serpapi": True},
        }
        F.sanear_resultado(res, F.urls_no_consultadas(PAGINAS))
        self.assertEqual(res["comparables"][0]["url"], "")
        self.assertEqual(res["comparables"][1]["url"], "https://www.lamudi.com.mx/casa-1")
        self.assertEqual(res["comparables_descartados"][0]["url"], "")
        self.assertEqual(res["comparables_descartados"][0]["motivo"], "")
        self.assertEqual(res["advertencias"], "Confianza media por pocos comparables.")
        self.assertEqual(res["recomendaciones"], ["Visita la zona."])
        self.assertNotIn("firecrawl", res)
        self.assertNotIn("proveedores_busqueda_configurados", res)
        texto = json.dumps(res, ensure_ascii=False).lower()
        for palabra in ("firecrawl", "bloque", "vivanuncios.com.mx/casa-3", "serpapi"):
            self.assertNotIn(palabra, texto)

    def test_sanear_resultado_formato_anterior_para_el_pdf(self):
        viejo = {
            "fuentes_consultadas": [
                {"url": "https://a.mx/1", "lectura": "leído", "estado_lectura": "ok", "provider": "tavily"},
                {"url": "https://b.mx/2", "lectura": "leído con Firecrawl", "estado_lectura": "ok_firecrawl"},
                {"url": "https://c.mx/3", "lectura": "bloqueado", "estado_lectura": "bloqueada_sin_firecrawl"},
            ],
            "comparables": [{"url": "https://c.mx/3", "fuente": "C"}],
            "firecrawl": {"activo": False, "motivo_no_uso": "falta FIRECRAWL_API_KEY"},
        }
        F.sanear_resultado(viejo)
        self.assertEqual([f["url"] for f in viejo["fuentes_consultadas"]], ["https://a.mx/1", "https://b.mx/2"])
        self.assertEqual(viejo["comparables"][0]["url"], "")
        self.assertNotIn("firecrawl", viejo)
        self.assertNotIn("tavily", json.dumps(viejo))
        # Se puede llamar dos veces sin cambiar nada más.
        antes = json.dumps(viejo, sort_keys=True)
        F.sanear_resultado(viejo)
        self.assertEqual(json.dumps(viejo, sort_keys=True), antes)


class CableadoTests(unittest.TestCase):
    def test_websearch_y_pdf_sanean(self):
        ws = (ROOT / "routers" / "avm_websearch.py").read_text(encoding="utf-8")
        self.assertIn('resultado["fuentes_consultadas"] = fuentes_publicas(paginas)', ws)
        self.assertIn("return sanear_resultado(resultado, urls_no_consultadas(paginas))", ws)
        self.assertNotIn('resultado["firecrawl"] =', ws)
        self.assertNotIn('"fetch_status": evidence_item.get("fetch_status"', ws)
        self.assertNotIn('detail=f"Error de Claude', ws)
        self.assertNotIn("SERPAPI_API_KEY, BRAVE_SEARCH_API_KEY o TAVILY_API_KEY.\",", ws)
        pdf = (ROOT / "routers" / "avm_pdf.py").read_text(encoding="utf-8")
        self.assertIn("resultado = sanear_resultado(dict(resultado))", pdf)

    def test_pantalla_sin_menciones_internas(self):
        html = (ROOT / "avm.html").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"firecrawl|scrap|bloque|robots", html, re.IGNORECASE))
        self.assertIn("Fuentes consultadas", html)


class SidebarClientesTests(unittest.TestCase):
    def test_clientes_vuelve_al_menu(self):
        js = (ROOT / "app-shell.js").read_text(encoding="utf-8")
        linea = next(l for l in js.splitlines() if "key:'clientes'" in l)
        self.assertNotIn("hidden:true", linea)
        self.assertIn("label:'Clientes'", linea)
        self.assertIn("requiere:'contactos'", linea)
        self.assertIn("const NAV_ALIAS = { 'crm-ajustes': 'contactos', alertas: 'contactos' };", js)
        self.assertIn("const mods = MODS.filter(m => visible(m) && norm(m.label).includes(nq))", js)


if __name__ == "__main__":
    unittest.main()
