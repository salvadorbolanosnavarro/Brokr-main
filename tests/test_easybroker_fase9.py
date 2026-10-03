"""Fase 9 del importador de EasyBroker: datos extra, re-importación sin pisar
lo trabajado en Broquer y propietario ligado sin duplicar."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from core.easybroker_mapping import _eb_to_brokr, eb_extras
from routers import easybroker_migration as M

EB = {"public_id": "EB-1", "title": "Casa", "internal_id": "MOR-9", "tags": ["destacada", " ", "remodelada"], "key_code": "Caja 3",
      "private_description": "Acepta 10% menos", "agent": {"email": "ana@x.mx", "full_name": "Ana"},
      "owner": {"full_name": "Juan Pérez", "phones": [{"phone": "443 111 2222"}], "email": "JUAN@X.MX"}}


class MapeoTests(unittest.TestCase):
    def test_columnas_y_extras(self):
        r = _eb_to_brokr(EB, "u1")
        self.assertEqual((r["clave_interna"], r["codigo_llave"], r["etiquetas"]), ("MOR-9", "Caja 3", ["destacada", "remodelada"]))
        x = eb_extras(EB)
        self.assertEqual(x["nota_privada"], "Acepta 10% menos")
        self.assertEqual(x["propietario"], {"nombre": "Juan Pérez", "telefono": "4431112222", "email": "juan@x.mx"})

    def test_sin_datos_no_inventa(self):
        r = _eb_to_brokr({"public_id": "EB-2"}, "u1")
        self.assertEqual((r["clave_interna"], r["codigo_llave"], r["etiquetas"]), (None, None, []))
        self.assertEqual(eb_extras({}), {"nota_privada": None, "agente": None, "propietario": None})


class FusionTests(unittest.TestCase):
    def test_reimportar_es_idempotente_y_respeta_broquer(self):
        prev = {"clave_interna": "PROPIA", "codigo_llave": "Gancho B", "etiquetas": ["vip"], "asignado_a": "u-prev"}
        inm = _eb_to_brokr({"public_id": "EB-1", "tags": ["destacada"]}, "u1")
        inm["notas"] = "Llamar al dueño"
        extras = {"nota_privada": "Acepta 10% menos"}
        M.fusionar_fase9(inm, prev, extras, None)
        self.assertEqual((inm["clave_interna"], inm["codigo_llave"], inm["asignado_a"]), ("PROPIA", "Gancho B", "u-prev"))
        self.assertEqual(inm["etiquetas"], ["vip", "destacada"])
        self.assertIn("Llamar al dueño", inm["notas"])
        self.assertIn("Acepta 10% menos", inm["notas"])
        # Segunda vuelta con las notas ya guardadas: no se repite.
        inm2 = _eb_to_brokr({"public_id": "EB-1", "tags": ["destacada"]}, "u1")
        inm2["notas"] = inm["notas"]
        M.fusionar_fase9(inm2, dict(prev, etiquetas=inm["etiquetas"]), extras, "u-ana")
        self.assertEqual(inm2["notas"].count("Acepta 10% menos"), 1)
        self.assertEqual(inm2["etiquetas"], ["vip", "destacada"])
        self.assertEqual(inm2["asignado_a"], "u-ana")


class PropietarioTests(unittest.TestCase):
    def test_crea_una_vez_y_liga_sin_duplicar(self):
        db = {"propiedades": [{"id": "p1", "eb_public_id": "EB-1"}], "contactos": [], "contactos_propiedades": []}

        async def get_rows(t, params, timeout=None):
            if t == "contactos_propiedades":
                return [x for x in db[t] if x["contacto_id"] == params["contacto_id"][3:] and x["propiedad_id"] == params["propiedad_id"][3:]]
            return list(db[t])

        async def post_rows(t, fila, **k):
            fila = dict(fila, id=f"{t}-{len(db[t]) + 1}")
            db[t].append(fila)
            return [fila]

        dueno = eb_extras(EB)["propietario"]
        with mock.patch("core.database.post_rows", post_rows):
            for _ in range(2):
                n, err = asyncio.run(M.ligar_propietarios("o1", "u1", {"EB-1": dueno}, get_rows))
                self.assertEqual((n, err), (1, []))
        self.assertEqual(len(db["contactos"]), 1)
        self.assertEqual(db["contactos"][0]["tipo"], "arrendador")
        self.assertEqual([(x["propiedad_id"], x["relacion"]) for x in db["contactos_propiedades"]], [("p1", "propietario")])


if __name__ == "__main__":
    unittest.main()
