"""Motor de coincidencias requerimiento ↔ inmueble."""
from __future__ import annotations

import unittest

from core.coincidencias import coincide

CASA = {"estatus": "activa", "tipo": "casa", "subtipo": "casa_condominio", "colonia": "Altozano", "ciudad": "Morelia",
        "operaciones": [{"tipo": "venta", "precio": 4_500_000, "moneda": "MXN"}, {"tipo": "renta", "precio": 28_000, "moneda": "MXN"}],
        "recamaras": 3, "banos": 2.5, "estacionamientos": 2, "m2_construccion": 220, "caracteristicas": ["alberca", "fin_infonavit"]}


class CoincidenciasTests(unittest.TestCase):
    def test_coincide_con_todo(self):
        req = {"operaciones": ["venta"], "tipos": ["casa"], "zonas": ["altozano"], "precio_min": 4_000_000, "precio_max": 5_000_000,
               "moneda": "MXN", "recamaras_min": 3, "caracteristicas": ["fin_infonavit"]}
        ok, motivos = coincide(req, CASA)
        self.assertTrue(ok, motivos)

    def test_tipo_especifico_no_acepta_otro(self):
        # "Casa" (tipo general) acepta sus variantes; uno específico, sólo ese.
        self.assertTrue(coincide({"tipos": ["casa"]}, dict(CASA, subtipo="villa", tipo="casa"))[0])
        self.assertFalse(coincide({"tipos": ["casa_condominio"]}, dict(CASA, subtipo="villa"))[0])
        self.assertFalse(coincide({"tipos": ["departamento"]}, CASA)[0])
        self.assertTrue(coincide({"tipos": ["casa_condominio"]}, CASA)[0])

    def test_presupuesto_por_operacion_y_moneda(self):
        self.assertTrue(coincide({"operaciones": ["renta"], "precio_max": 30_000}, CASA)[0])
        self.assertFalse(coincide({"operaciones": ["venta"], "precio_max": 30_000}, CASA)[0])
        self.assertFalse(coincide({"operaciones": ["venta"], "precio_max": 5_000_000, "moneda": "USD"}, CASA)[0])

    def test_zonas_varias_y_acentos(self):
        self.assertTrue(coincide({"zonas": ["Tres Marías", "Altozano"]}, CASA)[0])
        self.assertFalse(coincide({"zonas": ["Zapopan"]}, CASA)[0])

    def test_caracteristicas_y_comision(self):
        self.assertFalse(coincide({"caracteristicas": ["elevador"]}, CASA)[0])
        self.assertFalse(coincide({"solo_comision_compartida": True}, CASA)[0])
        self.assertTrue(coincide({"solo_comision_compartida": True}, dict(CASA, en_bolsa=True))[0])

    def test_inmueble_viejo_sin_columnas_nuevas(self):
        viejo = {"estatus": "activa", "tipo": "departamento", "operacion": "venta", "precio": 1_800_000, "ciudad": "Zapopan",
                 "amenidades": ["Alberca", "Elevador"]}
        self.assertTrue(coincide({"operacion": "venta", "tipo_inmueble": "departamento", "ciudad": "zapopan",
                                  "precio_max": 2_000_000, "caracteristicas": ["elevador"]}, viejo)[0])

    def test_no_activo_no_coincide(self):
        self.assertFalse(coincide({}, dict(CASA, estatus="vendida"))[0])


if __name__ == "__main__":
    unittest.main()
