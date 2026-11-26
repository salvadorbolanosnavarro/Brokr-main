"""Normalización de anuncios (core/acm_mercado.py) y base propia de
comparables (routers/acm_datos.py) con una base de datos falsa en memoria."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest import mock

from core import acm_mercado as mercado

try:
    from routers import acm_datos as datos
except ImportError:  # pragma: no cover - sin fastapi instalado
    datos = None


class MercadoTests(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(mercado.numero("$3,450,000"), 3_450_000)
        self.assertEqual(mercado.numero("3.4 mdp"), 3_400_000)
        self.assertEqual(mercado.numero("1.234.567"), 1_234_567)
        self.assertEqual(mercado.numero("120,5"), 120.5)
        self.assertIsNone(mercado.numero("consultar"))
        self.assertIsNone(mercado.numero(-5))
        self.assertEqual(mercado.coordenada("-101.18", 180), -101.18)
        self.assertIsNone(mercado.coordenada(0, 90))
        self.assertIsNone(mercado.coordenada(95, 90))

    def test_tipo_por_la_primera_palabra(self):
        self.assertEqual(mercado.familia_tipo("", "Casa cerca de local comercial"), "casa")
        self.assertEqual(mercado.familia_tipo("", "Departamento en venta"), "departamento")
        self.assertEqual(mercado.familia_tipo("nave_industrial"), "bodega")
        self.assertEqual(mercado.familia_tipo("", "algo raro"), "otro")

    def test_bloque_estructurado_sin_ia(self):
        texto = ("encabezado\nANUNCIOS ESTRUCTURADOS DE LA PÁGINA (alta confianza, 2 anuncios, ...):\n"
                 "1) Casa en venta | Chapultepec, Morelia | precio=3450000 | moneda=MXN | m2_construccion=150 | recamaras=3 | url=https://x.mx/a\n"
                 "2) Depto | precio=1200000\n\nresto de la página con precio=999")
        anuncios = mercado.parse_anuncios_estructurados(texto)
        self.assertEqual(len(anuncios), 2)
        self.assertEqual(anuncios[0]["ubicacion"], "Chapultepec, Morelia")
        self.assertEqual(anuncios[0]["url"], "https://x.mx/a")
        self.assertEqual(mercado.parse_anuncios_estructurados("sin bloque"), [])

    def test_comparable_desde_anuncio(self):
        zona = {"colonia": "Chapultepec", "ciudad": "Morelia", "pais": "MX", "tipo": "casa", "operacion": "venta"}
        c = mercado.comparable_desde_anuncio({"titulo": "Casa", "precio": "3450000", "m2_construccion": "150",
                                              "url": "/anuncio/1?utm=x"}, url_pagina="https://portal.mx/lista", zona=zona)
        self.assertEqual(c["url"], "https://portal.mx/anuncio/1")
        # El anuncio no dice su colonia: NO se le atribuye la buscada.
        self.assertEqual((c["tipo"], c["operacion"], c["colonia"], c["ubicacion_confirmada"]), ("casa", "venta", None, False))
        dice = mercado.comparable_desde_anuncio({"titulo": "Casa en Chapultepec con jardín", "precio": 3e6,
                                                 "m2_construccion": 150}, zona=zona)
        self.assertEqual((dice["colonia"], dice["ubicacion_confirmada"]), ("Chapultepec", True))
        self.assertIsNone(mercado.comparable_desde_anuncio({"precio": "3450000"}, zona=zona))       # sin m²
        self.assertIsNone(mercado.comparable_desde_anuncio({"precio": "9000", "m2_construccion": 100}, zona=zona))
        otra = mercado.comparable_desde_anuncio({"precio": 3e6, "m2_construccion": 100, "ubicacion": "Centro, Morelia"}, zona=zona)
        self.assertEqual(otra["colonia"], "Centro")
        con_calle = mercado.comparable_desde_anuncio({"precio": 3e6, "m2_construccion": 100,
                                                      "ubicacion": "Av. Camelinas 123, Col. Chapultepec Norte, Morelia"}, zona=zona)
        self.assertEqual(con_calle["colonia"], "Chapultepec Norte")
        solo_ciudad = mercado.comparable_desde_anuncio({"precio": 3e6, "m2_construccion": 100,
                                                        "ubicacion": "Morelia, Michoacán"}, zona=zona)
        self.assertFalse(solo_ciudad["ubicacion_confirmada"])

    def test_desde_propiedad_no_copia_datos_del_propietario(self):
        p = {"id": "p1", "tipo": "casa", "operacion": "venta", "precio": 3e6, "m2_construccion": 150,
             "lat": 19.7, "lng": -101.18, "fotos": ["https://f/1.jpg"], "propietario": {"nombre": "X"},
             "telefono": "443", "descripcion_privada": "secreto"}
        c = mercado.comparable_desde_propiedad(p, origen="inventario")
        self.assertEqual((c["lat"], c["lng"], c["precision_ubicacion"]), (19.7, -101.18, "exacta"))
        self.assertNotIn("propietario", c)
        self.assertNotIn("telefono", c)
        self.assertNotIn("secreto", str(c))

    def test_huella_reconoce_el_mismo_inmueble_aunque_baje_de_precio(self):
        a = {"ciudad": "Morelia", "colonia": "Chapultepec", "tipo": "casa", "operacion": "venta",
             "m2_construccion": 150, "recamaras": 3, "precio": 3_450_000}
        fila = {"id": "1", "huella": mercado.huella_comparable(a), "precio": 3_450_000}
        bajo = {**a, "precio": 3_150_000}
        self.assertIs(mercado.elegir_existente(bajo, [fila]), fila)
        otro = {**a, "precio": 2_400_000}                       # 30% menos: otro inmueble
        self.assertIsNone(mercado.elegir_existente(otro, [fila]))
        self.assertNotEqual(mercado.huella_comparable(a), mercado.huella_comparable({**a, "m2_construccion": 180}))


class BaseFalsa:
    """Interpreta los filtros de PostgREST que usa acm_datos."""

    def __init__(self):
        self.tablas = {"mercado_comparables": [], "mercado_precios_historial": [], "mercado_zonas": []}
        self.consultas = []
        self.n = 0

    @staticmethod
    def _cumple(fila, params):
        for k, v in params.items():
            if k in ("select", "order", "limit", "or", "and") or not isinstance(v, str):
                continue
            actual = fila.get(k)
            if v.startswith("eq."):
                if str(actual) != v[3:]:
                    return False
            elif v.startswith("lt."):
                if not (actual and str(actual) < v[3:]):
                    return False
            elif v == "is.null":
                if actual is not None:
                    return False
            elif v.startswith("in.("):
                valores = [x.strip('"').replace('\\"', '"') for x in v[4:-1].split('","')]
                if actual not in valores:
                    return False
        return True

    async def get_rows(self, tabla, params, **kw):
        self.consultas.append((tabla, dict(params)))
        return [dict(f) for f in self.tablas.get(tabla, []) if self._cumple(f, params)]

    async def post_rows(self, tabla, fila, **kw):
        self.n += 1
        fila = {**fila, "id": str(self.n)}
        self.tablas.setdefault(tabla, []).append(fila)
        return [dict(fila)]

    async def patch_rows(self, tabla, params, cambios, **kw):
        for f in self.tablas.get(tabla, []):
            if self._cumple(f, params):
                f.update(cambios)
        return []


@unittest.skipIf(datos is None, "fastapi no instalado")
class DatosTests(unittest.TestCase):
    def setUp(self):
        self.db = BaseFalsa()
        self.parches = [
            mock.patch.object(datos, "get_rows", self.db.get_rows),
            mock.patch.object(datos, "post_rows", self.db.post_rows),
            mock.patch.object(datos, "patch_rows", self.db.patch_rows),
            mock.patch.object(datos, "coordenadas_colonia", mock.AsyncMock(return_value=(19.70, -101.18))),
        ]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def anuncio(self, precio, **extra):
        return {"fuente": "portal", "tipo": "casa", "operacion": "venta", "precio": precio, "moneda": "MXN",
                "m2_construccion": 150, "recamaras": 3, "colonia": "Chapultepec", "ciudad": "Morelia",
                "pais": "MX", "url": "https://portal.mx/a", "ubicacion_confirmada": True, **extra}

    def test_guardar_inserta_actualiza_y_detecta_bajas(self):
        r = asyncio.run(datos.guardar_comparables([self.anuncio(3_450_000), self.anuncio(3_450_000)]))
        self.assertEqual(r, {"nuevos": 1, "actualizados": 0, "bajas": 0})     # duplicado del mismo lote
        fila = self.db.tablas["mercado_comparables"][0]
        self.assertEqual((fila["lat"], fila["precision_ubicacion"]), (19.70, "colonia"))
        self.assertEqual(fila["precio_inicial"], 3_450_000)

        r = asyncio.run(datos.guardar_comparables([self.anuncio(3_150_000)]))
        self.assertEqual(r, {"nuevos": 0, "actualizados": 1, "bajas": 1})
        self.assertEqual(fila["precio"], 3_150_000)
        self.assertEqual(fila["bajas_precio"], 1)
        self.assertEqual(fila["veces_visto"], 2)
        self.assertEqual(len(self.db.tablas["mercado_precios_historial"]), 2)

        r = asyncio.run(datos.guardar_comparables([self.anuncio(2_000_000)]))  # otro inmueble igualito
        self.assertEqual(r["nuevos"], 1)

    def test_sin_colonia_no_se_ubica_ni_se_confirma(self):
        asyncio.run(datos.guardar_comparables([self.anuncio(3e6, colonia=None, ubicacion_confirmada=False)]))
        fila = self.db.tablas["mercado_comparables"][0]
        self.assertIsNone(fila["lat"])
        self.assertFalse(fila["ubicacion_confirmada"])
        datos.coordenadas_colonia.assert_not_called()
        c = datos._fila_a_comparable({**fila, "ubicacion_confirmada": None})
        self.assertFalse(c["ubicacion_confirmada"])      # sin migración: nunca se presume confirmada

    def test_geocodificacion_rechaza_el_centro_de_la_ciudad(self):
        ciudad = {"types": ["locality", "political"], "address_components": [{"long_name": "Morelia", "types": ["locality"]}]}
        colonia = {"types": ["neighborhood", "political"], "address_components": [{"long_name": "Morelia", "types": ["locality"]}]}
        homonima = {"types": ["sublocality"], "address_components": [{"long_name": "Zamora", "types": ["locality"]}]}
        self.assertFalse(datos.resultado_es_de_colonia(ciudad, "Morelia"))
        self.assertTrue(datos.resultado_es_de_colonia(colonia, "Morelia"))
        self.assertFalse(datos.resultado_es_de_colonia(homonima, "Morelia"))

    def test_lo_inutil_no_se_guarda(self):
        r = asyncio.run(datos.guardar_comparables([self.anuncio(3e6, m2_construccion=None), self.anuncio(None)]))
        self.assertEqual(r["nuevos"], 0)
        self.assertEqual(self.db.tablas["mercado_comparables"], [])

    def test_marcar_retirados_exige_varias_corridas(self):
        viejo = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        reciente = datetime.now(timezone.utc).isoformat()
        for i, cuando in enumerate((viejo, reciente)):
            self.db.tablas["mercado_comparables"].append({
                "id": f"x{i}", "pais": "MX", "ciudad_norm": "morelia", "colonia_norm": "chapultepec", "tipo": "casa",
                "operacion": "venta", "estatus": "activo", "ultima_vez": cuando})
        zona = {"pais": "MX", "ciudad": "Morelia", "colonia": "Chapultepec", "tipo": "casa", "operacion": "venta"}
        self.assertEqual(asyncio.run(datos.marcar_retirados({**zona, "corridas": 2})), 0)
        self.assertEqual(asyncio.run(datos.marcar_retirados({**zona, "corridas": 3})), 1)
        viejo_f, reciente_f = self.db.tablas["mercado_comparables"]
        self.assertEqual((viejo_f["estatus"], viejo_f["retirado_en"]), ("retirado", viejo))
        self.assertEqual(reciente_f["estatus"], "activo")

    def test_busqueda_por_radio_se_amplia(self):
        sujeto = {"pais": "MX", "tipo": "casa", "operacion": "venta", "lat": 19.70, "lng": -101.18,
                  "m2_construccion": 150, "ciudad": "Morelia", "colonia": "Chapultepec"}
        asyncio.run(datos.comparables_de_mercado(sujeto))
        radios = [p for t, p in self.db.consultas if t == "mercado_comparables"]
        self.assertEqual(len(radios), 4)                                       # base vacía: llega a 6 km
        self.assertTrue(radios[0]["and"].startswith("(lat.gte."))
        self.assertIn("estatus.eq.retirado", radios[0]["or"])

    def test_filtros_seguros(self):
        self.assertEqual(datos._texto_filtro("Morelia),or=(1"), "Moreliaor1")
        self.assertEqual(datos._in_textos(['a "b"', "c"]), 'in.("a \\"b\\"","c")')
        self.assertEqual(datos._eq_o_nulo(""), "is.null")


if __name__ == "__main__":
    unittest.main()
