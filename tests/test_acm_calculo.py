"""Motor del ACM (core/acm_calculo.py): matemática fija y explicable."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from core import acm_calculo as calc

HOY = datetime(2026, 11, 26, tzinfo=timezone.utc)
SUJETO = {
    "tipo": "casa", "operacion": "venta", "colonia": "Chapultepec", "ciudad": "Morelia",
    "lat": 19.70, "lng": -101.18, "m2_construccion": 150, "m2_terreno": 130,
    "recamaras": 3, "banos": 2, "estacionamientos": 2, "antiguedad": 10,
    "conservacion": "bueno", "moneda": "MXN",
}


def comp(i, precio, m2c=150, **extra):
    base = {
        "id": f"c{i}", "origen": "mercado", "tipo": "casa", "operacion": "venta", "precio": precio,
        "moneda": "MXN", "m2_construccion": m2c, "recamaras": 3, "banos": 2, "estacionamientos": 2,
        "antiguedad": 10, "lat": 19.70 + i * 0.001, "lng": -101.18, "primera_vez": "2026-09-01",
        "ultima_vez": "2026-11-20", "estatus": "activo",
    }
    base.update(extra)
    return base


class UtilidadesTests(unittest.TestCase):
    def test_percentil_ponderado_con_pesos_iguales_es_el_clasico(self):
        pares = [(v, 1) for v in (10, 20, 30, 40, 50)]
        self.assertEqual(calc.percentil_ponderado(pares, 0.5), 30)
        self.assertEqual(calc.percentil_ponderado([(7, 1)], 0.25), 7)
        self.assertIsNone(calc.percentil_ponderado([], 0.5))

    def test_percentil_ponderado_se_inclina_al_mas_parecido(self):
        self.assertGreater(calc.percentil_ponderado([(10, 1), (20, 9)], 0.5), 15)

    def test_distancia_haversine(self):
        d = calc.distancia_m(19.70, -101.18, 19.71, -101.18)
        self.assertAlmostEqual(d, 1112, delta=5)
        self.assertIsNone(calc.distancia_m(None, 1, 2, 3))

    def test_redondeo_por_operacion(self):
        self.assertEqual(calc.redondear(3_456_789, "venta"), 3_460_000)
        self.assertEqual(calc.redondear(456_789, "venta"), 457_000)
        self.assertEqual(calc.redondear(18_740, "renta"), 18_700)

    def test_superficie_en_la_misma_base_que_el_sujeto(self):
        sup, base = calc.superficie_base(SUJETO)
        self.assertEqual((sup, base), (150, "construccion"))
        solo_terreno = comp(1, 3_000_000, m2c=None, m2_terreno=200)
        self.assertIsNone(calc.precio_m2(solo_terreno, base))
        self.assertFalse(calc.compatible(SUJETO, solo_terreno))
        terreno = {"tipo": "terreno", "m2_terreno": 300}
        self.assertEqual(calc.superficie_base(terreno), (300, "terreno"))


class AjustesTests(unittest.TestCase):
    def test_signos_de_los_ajustes(self):
        mas_grande = comp(1, 4_000_000, m2c=200, recamaras=4)
        aj = {a["concepto"]: a["pct"] for a in calc.ajustes_automaticos(SUJETO, mas_grande, 5)}
        self.assertGreater(aj["Superficie"], 0)       # más grande → su $/m² es menor → sube
        self.assertLess(aj["Recámaras"], 0)           # tiene una recámara más que el sujeto → baja
        self.assertEqual(aj["Negociación"], -5)

    def test_cierre_real_no_lleva_negociacion(self):
        cierre = comp(1, 3_000_000, origen="cierre", precio_cierre=3_000_000)
        conceptos = {a["concepto"] for a in calc.ajustes_automaticos(SUJETO, cierre, 5)}
        self.assertNotIn("Negociación", conceptos)

    def test_topes(self):
        enorme = comp(1, 9_000_000, m2c=1000)
        aj = {a["concepto"]: a["pct"] for a in calc.ajustes_automaticos(SUJETO, enorme, 0)}
        self.assertEqual(aj["Superficie"], calc.TOPE_SUPERFICIE)

    def test_lo_que_edita_el_asesor_manda(self):
        auto = [{"concepto": "Superficie", "pct": 3.0, "auto": True}, {"concepto": "Negociación", "pct": -5, "auto": True}]
        actuales = [{"concepto": "Negociación", "pct": 0, "auto": False}, {"concepto": "Alberca", "pct": "4.5", "auto": False}]
        r = calc.combinar_ajustes(auto, actuales)
        por = {a["concepto"]: a for a in r}
        self.assertEqual(por["Superficie"]["pct"], 3.0)
        self.assertEqual(por["Negociación"]["pct"], 0)      # eliminado = 0 manual, no vuelve
        self.assertFalse(por["Negociación"]["auto"])
        self.assertEqual(por["Alberca"]["pct"], 4.5)
        self.assertEqual(calc.combinar_ajustes([], [{"concepto": "x", "pct": 500}])[0]["pct"], 50.0)


class SeleccionYCalculoTests(unittest.TestCase):
    def candidatos(self):
        lista = [comp(i, 3_000_000 + i * 50_000) for i in range(12)]
        lista.append(comp(99, 15_000_000))                                   # atípico
        lista.append(comp(98, 3_000_000, operacion="renta"))                 # otra operación
        lista.append(comp(97, 3_000_000, tipo="departamento"))               # otro tipo
        lista.append(comp(96, 3_000_000, m2c=400))                           # fuera de ±2x
        lista.append(comp(95, 3_100_000, origen="cierre", precio_cierre=3_050_000,
                          lat=19.75, publicada_en="2026-03-01", fecha_cierre="2026-06-01"))
        return lista

    def test_seleccion_filtra_y_excluye_atipicos(self):
        sel = calc.seleccionar(SUJETO, self.candidatos(), 5, HOY)
        ids = {c["id"] for c in sel}
        self.assertNotIn("c98", ids)
        self.assertNotIn("c97", ids)
        self.assertNotIn("c96", ids)
        atipico = next(c for c in sel if c["id"] == "c99")
        self.assertFalse(atipico["incluido"])
        self.assertTrue(atipico["atipico"])
        self.assertTrue(next(c for c in sel if c["id"] == "c95")["incluido"])  # cierre real lejano entra
        self.assertLessEqual(sum(c["incluido"] for c in sel), calc.MAX_INCLUIDOS_INICIAL + calc.MAX_CIERRES_EXTRA)

    def test_calculo_es_determinista_y_coherente(self):
        sel = calc.seleccionar(SUJETO, self.candidatos(), 5, HOY)
        a = calc.calcular(SUJETO, sel, None, HOY)["resultado"]
        b = calc.calcular(SUJETO, sel, None, HOY)["resultado"]
        self.assertEqual(a, b)
        v, pm2 = a["valor"], a["precio_m2"]
        self.assertLessEqual(v["bajo"], v["medio"])
        self.assertLessEqual(v["medio"], v["alto"])
        self.assertAlmostEqual(v["medio"], calc.redondear(pm2["mediana"] * 150, "venta"), delta=10_000)
        self.assertEqual(a["estrategia_sugerida"]["mercado"]["precio"], v["medio"])
        self.assertIn(a["confianza"], ("alta", "media"))

    def test_conservacion_y_ajuste_general_mueven_el_valor(self):
        sel = calc.seleccionar(SUJETO, self.candidatos(), 5, HOY)
        base = calc.calcular(SUJETO, sel, None, HOY)["resultado"]["valor"]["medio"]
        remodelar = calc.calcular({**SUJETO, "conservacion": "remodelar"}, sel, None, HOY)["resultado"]["valor"]["medio"]
        self.assertAlmostEqual(remodelar / base, 0.85, delta=0.01)

    def test_excluir_un_comparable_cambia_el_resultado(self):
        sel = calc.seleccionar(SUJETO, self.candidatos(), 5, HOY)
        antes = calc.calcular(SUJETO, sel, None, HOY)["resultado"]["n_incluidos"]
        sel[0]["incluido"] = False
        self.assertEqual(calc.calcular(SUJETO, sel, None, HOY)["resultado"]["n_incluidos"], antes - 1)

    def test_otra_moneda_no_se_mezcla(self):
        r = calc.calcular(SUJETO, [comp(1, 200_000, moneda="USD", incluido=True)], None, HOY)
        self.assertFalse(r["comparables"][0]["incluido"])
        self.assertEqual(r["resultado"]["confianza"], "sin_datos")
        self.assertIsNone(r["resultado"]["valor"]["medio"])

    def test_sin_comparables_no_truena(self):
        r = calc.calcular(SUJETO, [], None, HOY)["resultado"]
        self.assertEqual(r["n_incluidos"], 0)
        self.assertIsNone(r["valor"]["bajo"])


class MercadoTests(unittest.TestCase):
    def test_grupos(self):
        self.assertEqual(calc.grupo_de(comp(1, 1, estatus="retirado"), HOY), "vendido")
        self.assertEqual(calc.grupo_de(comp(1, 1, origen="cierre"), HOY), "vendido")
        self.assertEqual(calc.grupo_de(comp(1, 1, bajas_precio=1), HOY), "bajas")
        self.assertEqual(calc.grupo_de(comp(1, 1, primera_vez="2026-01-01"), HOY), "bajas")
        self.assertEqual(calc.grupo_de(comp(1, 1), HOY), "activo")

    def test_dias_en_mercado(self):
        self.assertEqual(calc.dias_en_mercado(comp(1, 1, estatus="retirado", retirado_en="2026-10-01"), HOY), 30)
        cierre = comp(1, 1, origen="cierre", publicada_en="2026-03-01", fecha_cierre="2026-03-31")
        self.assertEqual(calc.dias_en_mercado(cierre, HOY), 30)

    def test_calibracion_del_descuento(self):
        self.assertEqual(calc.calibrar_descuento([], "venta"), {"pct": 5.0, "fuente": "defecto", "n": 0})
        cierres = [{"tipo_operacion": "venta", "precio_publicacion": 100, "precio_cierre": c} for c in (92, 93, 92, 94, 90, 50)]
        r = calc.calibrar_descuento(cierres, "venta")
        self.assertEqual(r["fuente"], "cierres")
        self.assertEqual(r["n"], 5)                       # el 50% se descarta por absurdo
        self.assertEqual(r["pct"], 8.0)
        self.assertEqual(calc.calibrar_descuento(cierres, "renta")["fuente"], "defecto")

    def test_comparar_versiones(self):
        a = {"resultado": {"valor": {"medio": 3_000_000}}, "comparables": [{"id": "x", "grupo": "activo"}, {"id": "y"}]}
        n = {"resultado": {"valor": {"medio": 3_150_000}}, "comparables": [{"id": "x", "grupo": "vendido"}, {"id": "z"}]}
        r = calc.comparar_versiones(a, n)
        self.assertEqual(r["cambio_pct"], 5.0)
        self.assertEqual((r["comparables_nuevos"], r["comparables_que_salieron"], r["se_vendieron_o_retiraron"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
