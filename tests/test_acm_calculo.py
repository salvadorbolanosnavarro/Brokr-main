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
                          lat=19.708, publicada_en="2026-03-01", fecha_cierre="2026-06-01"))
        lista.append(comp(94, 3_000_000, origen="cierre", precio_cierre=2_900_000,
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
        self.assertTrue(next(c for c in sel if c["id"] == "c95")["incluido"])   # cierre real de la zona entra
        lejano = next(c for c in sel if c["id"] == "c94")                       # a 5.5 km: se ve, no se incluye
        self.assertFalse(lejano["incluido"])
        self.assertIn("Fuera de la zona", lejano["motivo"])
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


class ZonaTests(unittest.TestCase):
    """Caso real: el asesor puso Chapultepec Sur y el análisis comparó con
    colonias de otra zona de la ciudad."""

    SUJETO = {**SUJETO, "colonia": "Chapultepec Sur"}

    def test_familia_de_colonias(self):
        self.assertEqual(calc.familia_colonia("Chapultepec Sur"), "chapultepec")
        self.assertEqual(calc.familia_colonia("Col. Chapultepec Oriente"), "chapultepec")
        self.assertEqual(calc.familia_colonia("Lomas de las Américas 2a Sección"), "lomas americas")
        self.assertNotEqual(calc.familia_colonia("Félix Ireta"), calc.familia_colonia("Chapultepec Norte"))

    def test_sin_ubicacion_confirmada_no_hay_cercania(self):
        supuesto = comp(1, 3e6, lat=19.70, lng=-101.18, colonia="Chapultepec Sur", ubicacion_confirmada=False)
        self.assertIsNone(calc.distancia_comparable(self.SUJETO, supuesto))
        centro_ciudad = comp(2, 3e6, precision_ubicacion="ciudad", colonia="Otra")
        self.assertIsNone(calc.distancia_comparable(self.SUJETO, centro_ciudad))
        hermana = comp(3, 3e6, lat=None, lng=None, colonia="Chapultepec Oriente")
        self.assertEqual(calc.distancia_comparable(self.SUJETO, hermana), calc.DISTANCIA_COLONIA_HERMANA_M)

    def test_lo_lejano_y_lo_no_confirmado_no_entra_solo(self):
        cerca = [comp(i, 3_000_000 + i * 40_000, lat=19.70 + i * 0.0015, colonia="Chapultepec Oriente") for i in range(6)]
        otra_zona = [comp(50 + i, 2_000_000, lat=19.66, lng=-101.23, colonia="Tres Puentes") for i in range(8)]
        sin_ubicacion = [comp(80 + i, 3_100_000, lat=None, lng=None, colonia=None, ubicacion_confirmada=False) for i in range(5)]
        sel = calc.seleccionar(self.SUJETO, cerca + otra_zona + sin_ubicacion, 5, HOY)
        incluidos = {c["id"] for c in sel if c["incluido"]}
        self.assertEqual(incluidos, {f"c{i}" for i in range(6)})
        for c in sel:
            if c["id"] in incluidos:
                continue
            self.assertIn(c["motivo"], ("Ubicación no confirmada en el anuncio",) if c["distancia_m"] is None
                          else (f"Fuera de la zona ({c['distancia_m'] / 1000:.1f} km)",))

    def test_cierre_real_tiene_radio_minimo_de_2km(self):
        cerca = [comp(i, 3e6 + i * 1000, lat=19.70 + i * 0.001, colonia="X") for i in range(6)]
        cierre = comp(90, 3e6, origen="cierre", precio_cierre=3e6, lat=19.7135, colonia="Y")      # ~1.5 km
        cierre_lejos = comp(91, 3e6, origen="cierre", precio_cierre=3e6, lat=19.73, colonia="Z")  # ~3.3 km
        sel = {c["id"]: c for c in calc.seleccionar(self.SUJETO, cerca + [cierre, cierre_lejos], 5, HOY)}
        self.assertTrue(sel["c90"]["incluido"])
        self.assertFalse(sel["c91"]["incluido"])

    def test_marca_fuera_de_zona(self):
        r = calc.calcular(self.SUJETO, [
            comp(1, 3e6, colonia="Chapultepec Oriente"),                                  # cerca
            comp(2, 3e6, lat=19.745, colonia="Lejana"),                                   # ~5 km
            comp(3, 3e6, lat=None, lng=None, colonia=None, ubicacion_confirmada=False),   # sin ubicación
            {**comp(4, 3e6, lat=None, lng=None, colonia=None), "origen": "manual"},       # manual: nunca fuera
        ], None, HOY)
        self.assertEqual([c["fuera_zona"] for c in r["comparables"]], [False, True, True, False])

    def test_el_radio_crece_solo_si_hace_falta(self):
        a_1500 = [comp(i, 3e6 + i * 1000, lat=19.70 + 0.0135, colonia="X") for i in range(6)]   # ~1.5 km
        sel = calc.seleccionar(self.SUJETO, a_1500, 5, HOY)
        self.assertTrue(all(c["incluido"] for c in sel))
        a_5km = [comp(i, 3e6 + i * 1000, lat=19.745, colonia="X") for i in range(6)]
        self.assertFalse(any(c["incluido"] for c in calc.seleccionar(self.SUJETO, a_5km, 5, HOY)))


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
