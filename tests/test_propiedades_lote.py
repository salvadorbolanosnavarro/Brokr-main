"""Acciones en lote de inmuebles: sólo dueño o compañeros de la organización."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

import routers.propiedades_actualizar as mod


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


FILAS = [
    {"id": "a1", "user_id": "yo", "org_id": "org1", "etiquetas": ["x"]},
    {"id": "a2", "user_id": "companero", "org_id": "org1", "etiquetas": []},
    {"id": "b1", "user_id": "otro", "org_id": "org2", "etiquetas": []},
]


class PropiedadesLoteTests(unittest.TestCase):
    def setUp(self):
        self.parches = []
        self.patch_calls = []

        async def fake_uid(request):
            return "yo"

        async def fake_ctx(uid):
            return {"org_id": "org1", "activo": True}

        async def fake_get_rows(tabla, params, timeout=None):
            ids = params["id"][len("in.("):-1].split(",")
            return [f for f in FILAS if f["id"] in ids]

        async def fake_patch(tabla, params, cambios, prefer=None, timeout=None):
            self.patch_calls.append((params, cambios))
            v = params["id"]
            ids = v[len("in.("):-1].split(",") if v.startswith("in.") else [v[3:]]
            return [{"id": i} for i in ids]

        for nombre, f in (("get_user_id_from_token", fake_uid), ("get_org_context", fake_ctx),
                          ("get_rows", fake_get_rows), ("patch_rows", fake_patch)):
            p = mock.patch.object(mod, nombre, f)
            p.start()
            self.parches.append(p)

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def run_lote(self, body):
        return asyncio.run(mod.propiedades_lote(_Req(body)))

    def test_no_toca_inmuebles_de_otra_organizacion(self):
        out = self.run_lote({"ids": ["a1", "a2", "b1"], "set": {"estatus": "reservada"}})
        self.assertEqual(out, {"actualizadas": 2, "sin_permiso": 1})
        tocados = ",".join(p["id"] for p, _ in self.patch_calls)
        self.assertNotIn("b1", tocados)

    def test_etiquetas_agregar_y_quitar(self):
        self.run_lote({"ids": ["a1"], "etiquetas_agregar": ["nueva"], "etiquetas_quitar": ["x"]})
        self.assertEqual(self.patch_calls[-1][1]["etiquetas"], ["nueva"])

    def test_rechaza_campos_no_permitidos_y_estatus_invalido(self):
        with self.assertRaises(HTTPException):
            self.run_lote({"ids": ["a1"], "set": {"user_id": "hack"}})
        with self.assertRaises(HTTPException):
            self.run_lote({"ids": ["a1"], "set": {"estatus": "borrada"}})

    def test_ids_maliciosos_se_descartan(self):
        with self.assertRaises(HTTPException):
            self.run_lote({"ids": ["a1),or(user_id.neq.x"], "set": {"estatus": "activa"}})


if __name__ == "__main__":
    unittest.main()
