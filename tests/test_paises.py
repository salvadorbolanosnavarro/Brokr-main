"""Broquer en 5 países: la configuración del navegador y la del servidor
dicen lo mismo, y los cálculos de impuestos por país dan lo esperado."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core import paises


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _node(script: str):
    out = subprocess.run([NODE, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node no está instalado")
class PaisesEspejoTests(unittest.TestCase):
    def test_paises_js_y_core_paises_coinciden(self):
        js = _node(
            "global.window={};global.localStorage={getItem(){return null},setItem(){}};"
            "require('./paises.js');console.log(JSON.stringify(window.BK_PAISES))"
        )
        self.assertEqual(set(js), set(paises.PAISES))
        for codigo, cfg in paises.PAISES.items():
            with self.subTest(pais=codigo):
                self.assertEqual(js[codigo]["moneda"], cfg["moneda"])
                self.assertEqual(js[codigo]["lada"], cfg["lada"])
                self.assertEqual(js[codigo]["digitosTel"], cfg["digitos_tel"])
                self.assertEqual(js[codigo]["idFiscal"], cfg["id_fiscal"])
                self.assertEqual(js[codigo]["monedas"], list(cfg["monedas"]))

    def test_mexico_conserva_todos_sus_modulos(self):
        js = _node(
            "global.window={};global.localStorage={getItem(){return null},setItem(){}};"
            "require('./paises.js');console.log(JSON.stringify(window.BK_PAISES))"
        )
        self.assertEqual(js["MX"]["sinModulos"], ["impuestos"])
        for codigo in ("CO", "PE", "AR", "CL"):
            self.assertIn("isr", js[codigo]["sinModulos"])
            self.assertIn("cumplimiento", js[codigo]["sinModulos"])


@unittest.skipUnless(NODE, "node no está instalado")
class ImpuestosReglasTests(unittest.TestCase):
    def calc(self, pais: str, datos: dict) -> dict:
        return _node(
            "const I=require('./impuestos-reglas.js');"
            f"console.log(JSON.stringify(I.calcular({json.dumps(pais)},{json.dumps(datos)})))"
        )

    def test_colombia_ganancia_ocasional_15(self):
        r = self.calc("CO", {"venta": 500_000_000, "costo": 300_000_000,
                             "fechaCompra": "2015-01-01", "fechaVenta": "2026-06-01"})
        self.assertAlmostEqual(r["impuesto"], 30_000_000)
        self.assertAlmostEqual(r["retencion"], 5_000_000)

    def test_colombia_casa_habitacion_exenta_hasta_5000_uvt(self):
        r = self.calc("CO", {"venta": 600_000_000, "costo": 200_000_000, "casaHabitacion": True,
                             "reinvierte": True, "fechaCompra": "2010-01-01", "uvt": 52374})
        exenta = 5000 * 52374
        self.assertAlmostEqual(r["impuesto"], (400_000_000 - exenta) * 0.15)

    def test_colombia_menos_de_dos_anios_es_renta_ordinaria(self):
        r = self.calc("CO", {"venta": 100, "costo": 50, "fechaCompra": "2026-01-01", "fechaVenta": "2026-06-01"})
        self.assertIsNone(r["impuesto"])

    def test_peru_5_por_ciento_y_casa_exenta(self):
        r = self.calc("PE", {"venta": 800_000, "costo": 500_000, "fechaCompra": "2012-05-01"})
        self.assertAlmostEqual(r["impuesto"], 15_000)
        self.assertAlmostEqual(r["alcabala"], (800_000 - 10 * 5500) * 0.03)
        casa = self.calc("PE", {"venta": 800_000, "costo": 500_000, "fechaCompra": "2012-05-01",
                                "casaHabitacion": True})
        self.assertEqual(casa["impuesto"], 0)

    def test_peru_antes_de_2004_no_gravado(self):
        r = self.calc("PE", {"venta": 800_000, "costo": 100_000, "fechaCompra": "2001-03-01"})
        self.assertEqual(r["impuesto"], 0)

    def test_argentina_cedular_solo_desde_2018(self):
        r = self.calc("AR", {"venta": 200_000, "costo": 150_000, "fechaCompra": "2019-02-01"})
        self.assertAlmostEqual(r["impuesto"], 7_500)
        viejo = self.calc("AR", {"venta": 200_000, "costo": 150_000, "fechaCompra": "2010-02-01"})
        self.assertEqual(viejo["impuesto"], 0)

    def test_chile_tope_8000_uf_y_10_por_ciento(self):
        r = self.calc("CL", {"moneda": "UF", "venta": 15_000, "costo": 5_000,
                             "fechaCompra": "2010-01-01", "fechaVenta": "2026-01-01"})
        self.assertAlmostEqual(r["impuesto"], 200)  # (10.000 - 8.000) × 10%
        usado = self.calc("CL", {"moneda": "UF", "venta": 15_000, "costo": 5_000, "ufUsadas": 8_000,
                                 "fechaCompra": "2010-01-01", "fechaVenta": "2026-01-01"})
        self.assertAlmostEqual(usado["impuesto"], 1_000)

    def test_chile_en_pesos_convierte_el_tope(self):
        r = self.calc("CL", {"moneda": "CLP", "venta": 600_000_000, "costo": 200_000_000, "valorUf": 40_000,
                             "fechaCompra": "2010-01-01", "fechaVenta": "2026-01-01"})
        self.assertAlmostEqual(r["impuesto"], (400_000_000 - 8000 * 40_000) * 0.10)


class CorePaisesTests(unittest.IsolatedAsyncioTestCase):
    def test_pais_desconocido_es_mexico(self):
        self.assertEqual(paises.normalizar_pais(None), "MX")
        self.assertEqual(paises.normalizar_pais("zz"), "MX")
        self.assertEqual(paises.normalizar_pais(" co "), "CO")

    def test_telefono_usa_la_lada_del_pais(self):
        self.assertEqual(paises.telefono_e164("443 123 4567", "MX"), "+524431234567")
        self.assertEqual(paises.telefono_e164("52 443 123 4567", "MX"), "+524431234567")
        self.assertEqual(paises.telefono_e164("300 123 4567", "CO"), "+573001234567")
        self.assertEqual(paises.telefono_e164("912 345 678", "PE"), "+51912345678")
        self.assertEqual(paises.telefono_e164("9 1234 5678", "CL"), "+56912345678")
        self.assertEqual(paises.telefono_e164("+57 300 123 4567", "MX"), "+573001234567")

    async def test_pais_de_usuario_lee_el_perfil(self):
        with patch("core.paises.get_rows", new=AsyncMock(return_value=[{"pais": "PE"}])):
            self.assertEqual(await paises.pais_de_usuario("u1"), "PE")

    async def test_cuenta_sin_pais_es_mexico(self):
        with patch("core.paises.get_rows", new=AsyncMock(return_value=[{"pais": None}])):
            self.assertEqual(await paises.pais_de_usuario("u1"), "MX")
        with patch("core.paises.get_rows", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
            self.assertEqual(await paises.pais_de_usuario("u1"), "MX")


if __name__ == "__main__":
    unittest.main()


class CobroPorPaisTests(unittest.IsolatedAsyncioTestCase):
    async def _checkout(self, pais: str, plan: str, precio_usd: str = ""):
        from fastapi import HTTPException
        from routers import subscription_checkout as sc

        req = sc.CheckoutRequest(plan_id=plan, promo_code="ampi2026")
        with patch.object(sc, "STRIPE_SECRET_KEY", "sk_test"), \
             patch.object(sc, "STRIPE_PRICE_PRO", "price_mxn"), \
             patch.object(sc, "STRIPE_PRICE_AMPI", "price_ampi"), \
             patch.object(sc, "STRIPE_PRICE_PRO_USD", precio_usd), \
             patch.object(sc, "get_user_id_from_token", new=AsyncMock(return_value="u1")), \
             patch.object(sc, "pais_de_usuario", new=AsyncMock(return_value=pais)):
            with self.assertRaises(HTTPException) as ctx:
                await sc.subscription_checkout(req, request=None)
        return ctx.exception

    async def test_fuera_de_mexico_sin_precio_en_dolares_no_cobra_en_pesos(self):
        e = await self._checkout("CO", "max")
        self.assertEqual(e.status_code, 503)

    async def test_ampi_solo_en_mexico(self):
        e = await self._checkout("PE", "ampi")
        self.assertEqual(e.status_code, 400)
