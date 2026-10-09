"""Cierres: cálculo de comisión, reparto a Finanzas, permisos y cobro."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

import routers.cierres as K


class _Req:
    async def json(self):
        return {}


class PurosTests(unittest.TestCase):
    def test_comision_total(self):
        self.assertEqual(K.comision_total("pct", 5, 4_000_000), 200_000)
        self.assertEqual(K.comision_total("meses", 1, 28_000), 28_000)
        self.assertEqual(K.comision_total("monto", 150_000, None), 150_000)
        self.assertIsNone(K.comision_total("pct", None, 1))

    def test_reparto_solo_equipo(self):
        c = {"comision_inmobiliaria": 100, "opcionador_user_id": "u2", "opcionador_comision": 50,
             "asesor_user_id": None, "asesor_nombre": "Agencia X", "asesor_comision": 50}
        self.assertEqual(K.reparto(c, "dueno"), [{"user_id": "dueno", "beneficiario": "inmobiliaria", "monto": 100},
                                                 {"user_id": "u2", "beneficiario": "opcionador", "monto": 50}])


class FlujoTests(unittest.TestCase):
    def setUp(self):
        self.permiso = True
        self.db = {"propiedades": [{"id": "p1", "org_id": "o1", "user_id": "u1", "titulo": "Casa", "precio": 4_500_000, "operacion": "venta"}],
                   "organizacion_miembros": [{"org_id": "o1", "user_id": "u1", "rol_org": "owner", "activo": True}, {"org_id": "o1", "user_id": "u2", "rol_org": "agente", "activo": True}],
                   "cierres": [], "fin_movimientos": [], "actividades": []}

        async def uid(r):
            return "u1"

        async def ctx(u):
            return {"org_id": "o1", "activo": True, "rol_org": "agente", "permisos": {}}

        def permiso(c, k):
            return self.permiso if k == "ver_comisiones" else True

        async def get_rows(t, params, timeout=None):
            out = []
            for f in self.db.get(t, []):
                if all(str(f.get(k)).lower() == v[3:].lower() for k, v in params.items() if isinstance(v, str) and v.startswith("eq.")):
                    out.append(f)
            return out

        async def post_rows(t, fila, prefer=None, timeout=None):
            fila = dict(fila); fila.setdefault("id", f"{t}{len(self.db[t]) + 1}")
            self.db[t].append(fila)
            return [fila]

        async def patch_rows(t, params, cambios, prefer=None, timeout=None):
            out = []
            for f in self.db.get(t, []):
                if all(str(f.get(k)) == v[3:] for k, v in params.items() if v.startswith("eq.")):
                    f.update(cambios); out.append(f)
            return out

        self.parches = [mock.patch.object(K, n, f) for n, f in (
            ("get_user_id_from_token", uid), ("get_org_context", ctx), ("permiso_efectivo", permiso),
            ("get_rows", get_rows), ("post_rows", post_rows), ("patch_rows", patch_rows))]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_sin_permiso_no_ve_ni_guarda(self):
        self.permiso = False
        with self.assertRaises(HTTPException) as e:
            asyncio.run(K.guardar_cierre(K.CierreIn(propiedad_id="p1", estatus="vendida"), _Req()))
        self.assertEqual(e.exception.status_code, 403)

    def test_cierre_crea_por_cobrar_y_cobro_actualiza(self):
        body = K.CierreIn(propiedad_id="p1", estatus="vendida", precio_cierre=4_000_000, comision_tipo="pct", comision_valor=5,
                          comision_inmobiliaria=100_000, opcionador_user_id="u2", opcionador_comision=50_000,
                          asesor_nombre="Agencia X", asesor_comision=50_000)
        with mock.patch.object(K, "_revisar_pld", mock.AsyncMock(return_value={"genera_aviso": False})):
            r = asyncio.run(K.guardar_cierre(body, _Req()))
        self.assertEqual(r["cierre"]["comision_total"], 200_000)
        self.assertEqual(self.db["propiedades"][0]["estatus"], "vendida")
        movs = self.db["fin_movimientos"]
        self.assertEqual(sorted((m["user_id"], m["monto"], m["estado"]) for m in movs),
                         [("u1", 100_000, "por_cobrar"), ("u2", 50_000, "por_cobrar")])
        # Volver a guardar no duplica ingresos.
        with mock.patch.object(K, "_revisar_pld", mock.AsyncMock(return_value=None)):
            asyncio.run(K.guardar_cierre(body, _Req()))
        self.assertEqual(len(self.db["fin_movimientos"]), 2)
        # Cobrar ambos marca el cierre como cobrado.
        for m in list(movs):
            with mock.patch.object(K, "get_user_id_from_token", mock.AsyncMock(return_value=m["user_id"])):
                asyncio.run(K.marcar_cobrado(m["id"], _Req()))
        self.assertTrue(self.db["cierres"][-1]["cobrado"] or self.db["cierres"][0]["cobrado"])
        self.assertNotIn("por cobrar", movs[0]["concepto"])


if __name__ == "__main__":
    unittest.main()
