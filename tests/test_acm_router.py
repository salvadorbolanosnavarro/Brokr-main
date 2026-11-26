"""ACM: entrada saneada, permisos, privacidad del reporte y contratos de la plataforma."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from core import acm_reporte as reporte

ROOT = Path(__file__).resolve().parents[1]

try:
    from routers import acm
except ImportError:  # pragma: no cover - sin fastapi instalado
    acm = None


@unittest.skipIf(acm is None, "fastapi no instalado")
class EntradaTests(unittest.TestCase):
    def test_comparables_del_navegador_se_sanean(self):
        lista = acm._limpiar_comparables([{
            "id": "m-1", "origen": "mercado", "precio": "$3,000,000", "recamaras": "3", "lat": "19.7", "lng": "-101.1",
            "url": "javascript:alert(1)", "foto_url": "http://inseguro/x.jpg", "tipo": "Casa en condominio",
            "operacion": "permuta", "incluido": "si", "campo_raro": "x", "precio_m2_ajustado": 1,
            "ajustes": [{"concepto": "A" * 200, "pct": "4", "auto": 0}] * 20,
        }, "no soy un dict", {"precio": 1}])
        c = lista[0]
        self.assertEqual((c["precio"], c["recamaras"], c["lng"]), (3_000_000, 3, -101.1))
        self.assertIsNone(c["url"])
        self.assertIsNone(c["foto_url"])
        self.assertEqual(c["tipo"], "casa")
        self.assertIsNone(c["operacion"])
        self.assertNotIn("campo_raro", c)
        self.assertNotIn("precio_m2_ajustado", c)                 # los derivados los calcula el servidor
        self.assertEqual(len(c["ajustes"]), 12)
        self.assertEqual(len(c["ajustes"][0]["concepto"]), 60)
        self.assertEqual(len(lista), 2)
        self.assertEqual(lista[1]["origen"], "manual")
        self.assertTrue(lista[1]["id"].startswith("manual-"))
        self.assertEqual(len(acm._limpiar_comparables([{"precio": 1}] * 500)), acm.MAX_COMPARABLES)

    def test_estrategia_sigue_al_rango_salvo_lo_editado(self):
        resultado = {"estrategia_sugerida": {k: {"precio": p, "dias_estimados": None}
                                             for k, p in (("rapido", 1), ("mercado", 2), ("aspiracional", 3))}}
        guardada = {"elegida": "mercado", "precios": {"rapido": 9, "mercado": 9, "aspiracional": 30}, "editados": ["aspiracional"]}
        e = acm._estrategia(guardada, resultado)
        self.assertEqual(e["precios"], {"rapido": 1, "mercado": 2, "aspiracional": 30})
        self.assertEqual((e["precio_salida"], e["editados"]), (2, ["aspiracional"]))
        del_navegador = acm._estrategia({"elegida": "propio", "precio_salida": "3450000", "precios": {"rapido": 5}}, resultado)
        self.assertEqual((del_navegador["precios"]["rapido"], del_navegador["precio_salida"]), (5, 3_450_000))
        self.assertEqual(acm._estrategia({"elegida": "hackeo"}, resultado)["elegida"], "mercado")

    def test_quien_puede_ver_un_acm(self):
        fila = {"user_id": "u1", "org_id": "o1"}
        self.assertTrue(acm._puede_ver({"user_id": "u1", "org_id": None, "es_admin": False}, fila))
        self.assertTrue(acm._puede_ver({"user_id": "u2", "org_id": "o1", "es_admin": True}, fila))
        self.assertFalse(acm._puede_ver({"user_id": "u2", "org_id": "o1", "es_admin": False}, fila))
        self.assertFalse(acm._puede_ver({"user_id": "u2", "org_id": "o2", "es_admin": True}, fila))

    def test_sujeto_valida_lo_minimo(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            acm._sujeto(acm.SujetoIn(ciudad="Morelia"), "MX")                       # sin m²
        with self.assertRaises(HTTPException):
            acm._sujeto(acm.SujetoIn(m2_construccion=100), "MX")                    # sin ciudad
        s = acm._sujeto(acm.SujetoIn(ciudad="Morelia", m2_construccion=100, operacion="renta_temporal",
                                     ajuste_general_pct=99, lat=19.7, lng=None, propiedad_id="no-uuid"), "MX")
        self.assertEqual((s["operacion"], s["ajuste_general_pct"], s["lat"], s["propiedad_id"]), ("renta", 30.0, None, None))


class ReporteTests(unittest.TestCase):
    def fila(self):
        return {
            "sujeto": {"tipo": "casa", "operacion": "venta", "colonia": "Centro", "ciudad": "Morelia",
                       "lat": 19.7, "lng": -101.18, "m2_construccion": 150, "conservacion": "bueno"},
            "comparables": [
                {"id": "a", "incluido": True, "grupo": "activo", "titulo": "<script>alert(1)</script>", "precio": 3e6,
                 "precio_m2": 20000, "precio_m2_ajustado": 19000, "superficie": 150, "lat": 19.701, "lng": -101.18,
                 "ajustes": [{"concepto": "Superficie", "pct": -1}], "ajuste_total_pct": -1,
                 "nota": "NOTA-INTERNA-COMP"},
                {"id": "b", "incluido": False, "grupo": "activo", "titulo": "DESCARTADO", "precio": 9e6,
                 "precio_m2": 60000, "precio_m2_ajustado": 60000},
            ],
            "resultado": {"moneda": "MXN", "valor": {"bajo": 2.8e6, "medio": 3e6, "alto": 3.2e6},
                          "precio_m2": {"min": 18000, "p25": 19000, "mediana": 20000, "p75": 21000, "max": 22000},
                          "superficie": 150, "mercado": {"en_venta": 1}},
            "estrategia": {"elegida": "mercado", "precios": {"mercado": 3e6}, "precio_salida": 3e6},
            "nota_propietario": "Hola propietario",
            "notas_internas": "NOTA-INTERNA-ACM",
        }

    def test_el_propietario_solo_ve_lo_que_decide_el_asesor(self):
        html = reporte.render(self.fila(), {"nombre": "Asesor", "telefono": "4431234567"}, para_pdf=False)
        self.assertNotIn("NOTA-INTERNA-ACM", html)
        self.assertNotIn("NOTA-INTERNA-COMP", html)
        self.assertNotIn("DESCARTADO", html)
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Hola propietario", html)
        self.assertIn("https://wa.me/524431234567", html)
        self.assertIn("noindex", html)

    def test_pdf_sin_botones_y_marca_del_asesor(self):
        html = reporte.render(self.fila(), {"nombre": "Asesor", "logo_url": "https://x/logo.png"}, para_pdf=True)
        self.assertNotIn("window.print", html)
        self.assertIn("https://x/logo.png", html)
        self.assertNotIn("Broquer", html)
        sin_logo_inseguro = reporte.render(self.fila(), {"nombre": "A", "logo_url": "javascript:x"}, para_pdf=True)
        self.assertNotIn("javascript:x", sin_logo_inseguro)
        self.assertTrue(reporte.nombre_archivo(self.fila()).startswith("ACM_Centro_"))


class PlataformaTests(unittest.TestCase):
    def test_main_registra_los_routers(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("from routers.acm import router as acm_router", main)
        self.assertIn("from routers.acm_datos import router as acm_datos_router", main)

    def test_modulo_en_el_menu(self):
        shell = (ROOT / "app-shell.js").read_text(encoding="utf-8")
        self.assertIn("key:'acm',          href:'acm.html'", shell)
        self.assertIn("'acm':           { title:'Análisis comparativo'", shell)
        self.assertNotIn("avm.html", shell)                              # AVM viejo retirado
        self.assertFalse((ROOT / "avm.html").exists())
        html = (ROOT / "acm.html").read_text(encoding="utf-8")
        self.assertIn('data-app="acm"', html)
        self.assertIn('src="app-shell.js"', html)

    def test_migracion_con_rls_en_todas_las_tablas(self):
        sql = (ROOT / "migracion-acm.sql").read_text(encoding="utf-8")
        tablas = re.findall(r"create table if not exists public\.(\w+)", sql)
        self.assertEqual(len(tablas), 5)
        for t in tablas:
            self.assertIn(f"alter table public.{t} enable row level security;", sql)
        self.assertNotIn("create policy", sql)          # sólo el backend con service key

    def test_no_reconstruye_infraestructura(self):
        for ruta in ("routers/acm.py", "routers/acm_datos.py", "core/acm_calculo.py", "core/acm_mercado.py", "core/acm_reporte.py"):
            texto = (ROOT / ruta).read_text(encoding="utf-8")
            with self.subTest(ruta=ruta):
                self.assertNotRegex(texto, r"\bos\.(?:getenv|environ)\b")
                self.assertNotIn("/rest/v1/", texto)
                self.assertNotRegex(texto, r"async\s+def\s+get_user_id_from_token")

    def test_recoleccion_nocturna_apagada_por_defecto(self):
        import os
        from unittest import mock

        from core import config

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACM_RECOLECCION_ACTIVA", None)
            self.assertFalse(config.Settings.from_env().acm_recoleccion_enabled)
        with mock.patch.dict(os.environ, {"ACM_RECOLECCION_ACTIVA": "1", "ACM_RECOLECCION_HORA": "99"}):
            cfg = config.Settings.from_env()
            self.assertTrue(cfg.acm_recoleccion_enabled)
            self.assertEqual(cfg.acm_recoleccion_hora, 23)
        datos_src = (ROOT / "routers/acm_datos.py").read_text(encoding="utf-8")
        inicio = datos_src.index("async def _iniciar_recoleccion")
        self.assertIn("if not settings.acm_recoleccion_enabled:", datos_src[inicio:inicio + 600])

    def test_la_ia_no_calcula_valores(self):
        datos_src = (ROOT / "routers/acm_datos.py").read_text(encoding="utf-8")
        prompt = datos_src[datos_src.index("_PROMPT_EXTRAER"):datos_src.index('"""', datos_src.index("_PROMPT_EXTRAER") + 30)]
        self.assertIn("No calcules valores", prompt)
        self.assertNotIn("valor_estimado", datos_src)


if __name__ == "__main__":
    unittest.main()
