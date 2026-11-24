"""Calculadora avanzada de impuestos (impuestos-avanzada.js) y los arreglos de
la auditoría a las calculadoras simples (isr.html, impuestos-reglas.js)."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _node(script: str):
    out = subprocess.run([NODE, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def calc(pais: str, escenario: dict) -> dict:
    return _node(
        "const A=require('./impuestos-avanzada.js');"
        f"console.log(JSON.stringify(A.calcular({json.dumps(pais)},{json.dumps(escenario)})))"
    )


def simple(pais: str, datos: dict) -> dict:
    return _node(
        "const I=require('./impuestos-reglas.js');"
        f"console.log(JSON.stringify(I.calcular({json.dumps(pais)},{json.dumps(datos)})))"
    )


@unittest.skipUnless(NODE, "node no está instalado")
class ValoracionUsufructoTests(unittest.TestCase):
    def valor(self, pais, op):
        return _node(
            "const A=require('./impuestos-avanzada.js');"
            f"console.log(JSON.stringify(A.valorUsufructo({json.dumps(pais)},{json.dumps(op)})))"
        )["pct"]

    def test_colombia_art_303(self):
        self.assertAlmostEqual(self.valor("CO", {}), 0.70)
        self.assertAlmostEqual(self.valor("CO", {"tipo": "temporal", "anios": 6}), 0.30)
        self.assertAlmostEqual(self.valor("CO", {"tipo": "temporal", "anios": 30}), 0.70)

    def test_chile_escala_por_edad(self):
        self.assertAlmostEqual(self.valor("CL", {"edad": 25}), 0.9)
        self.assertAlmostEqual(self.valor("CL", {"edad": 72}), 0.4)

    def test_mexico_50_y_manual(self):
        self.assertAlmostEqual(self.valor("MX", {}), 0.5)
        self.assertAlmostEqual(self.valor("MX", {"metodo": "manual", "pct": 35}), 0.35)


@unittest.skipUnless(NODE, "node no está instalado")
class MexicoAvanzadaTests(unittest.TestCase):
    def test_usufructo_y_nuda_suman_el_precio(self):
        r = calc("MX", {"precio": 8_000_000, "fechaVenta": "2026-12-10", "tipo": "terreno", "udi": 8.6,
                        "titulares": [
                            {"derecho": "usufructo", "cuota": 100, "tramos": [{"fecha": "2010-01-01", "costo": 1, "factor": 1}]},
                            {"derecho": "nuda", "cuota": 50, "tramos": [{"fecha": "2010-01-01", "costo": 1, "factor": 1}]},
                            {"derecho": "nuda", "cuota": 50, "tramos": [{"fecha": "2010-01-01", "costo": 1, "factor": 1}]}]})
        self.assertAlmostEqual(r["vendido"], 8_000_000)
        self.assertEqual([round(t["titular"]["valor"]) for t in r["titulares"]], [4_000_000, 2_000_000, 2_000_000])

    def test_exencion_se_mide_contra_el_precio_no_la_ganancia(self):
        # Precio 10M > 700,000 UDIS × 8 = 5.6M: grava (10 − 5.6)/10 = 44% de la ganancia.
        r = calc("MX", {"precio": 10_000_000, "fechaVenta": "2026-12-10", "tipo": "terreno", "udi": 8,
                        "titulares": [{"cuota": 100, "casaHabitacion": True,
                                       "tramos": [{"fecha": "2010-01-01", "costo": 8_000_000, "factor": 1}]}]})
        t = r["titulares"][0]
        self.assertAlmostEqual(t["base"], 2_000_000 * 0.44, places=2)

    def test_tarifa_acumulada_al_mes_de_la_firma(self):
        # Misma operación: en marzo paga más que en diciembre (art. 126).
        base = {"precio": 5_000_000, "tipo": "terreno",
                "titulares": [{"cuota": 100, "tramos": [{"fecha": "2016-01-01", "costo": 2_000_000, "factor": 1}]}]}
        marzo = calc("MX", {**base, "fechaVenta": "2026-03-15"})["totalVendedores"]
        dic = calc("MX", {**base, "fechaVenta": "2026-12-15"})["totalVendedores"]
        self.assertGreater(marzo, dic)
        # Diciembre = tarifa anual: 3M ÷ 10 años = 300,000 → renglón 21.36%.
        esperado = (22282.14 + (300_000 - 210403.70) * 0.2136) * 10
        self.assertAlmostEqual(dic, esperado, places=0)

    def test_no_residente_25_por_ciento_del_precio(self):
        r = calc("MX", {"precio": 4_000_000, "fechaVenta": "2026-06-01",
                        "titulares": [{"cuota": 100, "residente": False, "tramos": [{"fecha": "2010-01-01", "costo": 1_000_000, "factor": 1.5}]}]})
        self.assertAlmostEqual(r["totalVendedores"], 1_000_000)

    def test_tramos_con_fechas_distintas_usan_sus_propios_anios(self):
        r = calc("MX", {"precio": 6_000_000, "fechaVenta": "2026-12-01", "tipo": "terreno",
                        "titulares": [{"cuota": 100, "tramos": [
                            {"fecha": "2004-01-01", "costo": 1_000_000, "factor": 1, "pct": 50},
                            {"fecha": "2024-01-01", "costo": 2_000_000, "factor": 1, "pct": 50}]}]})
        lineas = [l["l"] for l in r["titulares"][0]["lineas"]]
        self.assertTrue(any("÷ 20 años" in l for l in lineas))
        self.assertTrue(any("÷ 2 años" in l for l in lineas))


@unittest.skipUnless(NODE, "node no está instalado")
class OtrosPaisesAvanzadaTests(unittest.TestCase):
    def test_colombia_avaluo_catastral_y_exencion_por_titular(self):
        r = calc("CO", {"precio": 900_000_000, "avaluo": 1_000_000_000, "fechaVenta": "2026-03-01", "uvt": 52374,
                        "titulares": [
                            {"cuota": 50, "casaHabitacion": True, "reinvierte": True, "tramos": [{"fecha": "2012-01-01", "costo": 200_000_000}]},
                            {"cuota": 50, "tramos": [{"fecha": "2012-01-01", "costo": 200_000_000}]}]})
        a, b = r["titulares"]
        self.assertAlmostEqual(b["impuesto"], 300_000_000 * 0.15)
        self.assertAlmostEqual(a["impuesto"], (300_000_000 - 5000 * 52374) * 0.15)

    def test_peru_casa_habitacion_requiere_dos_anios(self):
        r = calc("PE", {"precio": 900_000, "fechaVenta": "2026-03-01",
                        "titulares": [{"cuota": 100, "casaHabitacion": True, "tramos": [{"fecha": "2025-01-01", "costo": 500_000}]}]})
        self.assertAlmostEqual(r["totalVendedores"], 20_000)
        r = calc("PE", {"precio": 900_000, "fechaVenta": "2026-03-01",
                        "titulares": [{"cuota": 100, "casaHabitacion": True, "tramos": [{"fecha": "2020-01-01", "costo": 500_000}]}]})
        self.assertEqual(r["totalVendedores"], 0)

    def test_argentina_no_residente_toma_la_opcion_menor(self):
        r = calc("AR", {"precio": 200_000, "fechaVenta": "2026-03-01",
                        "titulares": [{"cuota": 100, "residente": False, "tramos": [{"fecha": "2019-01-01", "costo": 10_000}]}]})
        self.assertAlmostEqual(r["totalVendedores"], 200_000 * 0.9 * 0.15)

    def test_chile_tope_8000_uf_por_titular(self):
        r = calc("CL", {"precio": 30_000, "moneda": "UF", "fechaVenta": "2026-03-01",
                        "titulares": [{"cuota": 50, "tramos": [{"fecha": "2010-01-01", "costo": 2_000}]},
                                      {"cuota": 50, "ufUsadas": 8000, "tramos": [{"fecha": "2010-01-01", "costo": 2_000}]}]})
        a, b = r["titulares"]
        self.assertAlmostEqual(a["impuesto"], (13_000 - 8_000) * 0.10)
        self.assertAlmostEqual(b["impuesto"], 13_000 * 0.10)


@unittest.skipUnless(NODE, "node no está instalado")
class ArreglosCalculadoraSimpleTests(unittest.TestCase):
    def test_peru_casa_habitacion_con_menos_de_dos_anios_paga(self):
        r = simple("PE", {"venta": 800_000, "costo": 500_000, "fechaCompra": "2025-06-01",
                          "fechaVenta": "2026-01-01", "casaHabitacion": True})
        self.assertAlmostEqual(r["impuesto"], 15_000)

    def test_chile_en_pesos_sin_uf_no_inventa_el_impuesto(self):
        r = simple("CL", {"moneda": "CLP", "venta": 600_000_000, "costo": 200_000_000,
                          "fechaCompra": "2010-01-01", "fechaVenta": "2026-01-01"})
        self.assertIsNone(r["impuesto"])

    def test_colombia_avaluo_catastral_es_piso(self):
        r = simple("CO", {"venta": 100, "costo": 50, "avaluo": 200, "fechaCompra": "2010-01-01"})
        self.assertAlmostEqual(r["impuesto"], 150 * 0.15)


class IsrMexicoFuenteTests(unittest.TestCase):
    """isr.html no se puede ejecutar sin navegador: se revisa que la lógica corregida siga ahí."""

    def setUp(self):
        self.src = (ROOT / "isr.html").read_text(encoding="utf-8")

    def test_exencion_compara_el_precio(self):
        self.assertIn("if (venta<=LIMITE_EX)", self.src)
        self.assertNotIn("if (ganTotal<=LIMITE_EX)", self.src)

    def test_usa_tarifa_acumulada_al_mes(self):
        self.assertIn("getTarifaAlMes(anioV, mesV)", self.src)

    def test_exencion_es_visible(self):
        self.assertIn('<select id="f-exp">', self.src)


if __name__ == "__main__":
    unittest.main()
