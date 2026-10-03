"""Ciclo diario de alertas: detecta coincidencias nuevas una sola vez."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

import routers.alertas as A


class CicloAlertasTests(unittest.TestCase):
    def setUp(self):
        self.db = {
            "requerimientos_busqueda": [{"id": "r1", "org_id": "o1", "contacto_id": "c1", "user_id": "u1", "activo": True,
                                         "operaciones": ["venta"], "zonas": ["altozano"], "precio_max": 5_000_000,
                                         "ultima_alerta_en": None, "actualizado_en": "2026-09-01T00:00:00+00:00"}],
            "propiedades": [
                {"id": "p1", "org_id": "o1", "estatus": "activa", "colonia": "Altozano", "updated_at": "2026-10-01T00:00:00+00:00",
                 "operaciones": [{"tipo": "venta", "precio": 4_000_000, "moneda": "MXN"}]},
                {"id": "p2", "org_id": "o1", "estatus": "activa", "colonia": "Centro", "updated_at": "2026-10-01T00:00:00+00:00",
                 "operaciones": [{"tipo": "venta", "precio": 1_000_000, "moneda": "MXN"}]},
            ],
            "alertas_enviadas": [],
            "contactos": [{"id": "c1", "nombre": "ANA", "asignado_a": "u2"}],
        }
        self.push = []

        async def get_rows(t, params, timeout=None):
            filas = self.db.get(t, [])
            if t == "requerimientos_busqueda":
                return [r for r in filas if r.get("ultima_alerta_en") is None]
            if t == "propiedades" and params.get("en_bolsa"):
                return []
            if t == "alertas_enviadas":
                return [a for a in filas if a["requerimiento_id"] == params["requerimiento_id"][3:]]
            return list(filas)

        async def post_rows(t, filas, prefer=None, timeout=None):
            self.db[t].extend(filas if isinstance(filas, list) else [filas])
            return []

        async def patch_rows(t, params, cambios, prefer=None, timeout=None):
            for f in self.db[t]:
                if f["id"] == params["id"][3:]:
                    f.update(cambios)
            return []

        self.parches = [mock.patch.object(A, n, f) for n, f in (("get_rows", get_rows), ("post_rows", post_rows), ("patch_rows", patch_rows))]
        for p in self.parches:
            p.start()

        async def fake_push(uid, t, c, d=None, badge=None):
            self.push.append((uid, c))
        import push
        self.p_push = mock.patch.object(push, "enviar_push", fake_push)
        self.p_push.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self.p_push.stop()

    def test_detecta_una_vez_y_avisa_al_agente(self):
        n = asyncio.run(A.revisar_alertas())
        self.assertEqual(n, 1)
        self.assertEqual([a["propiedad_id"] for a in self.db["alertas_enviadas"]], ["p1"])
        self.assertEqual(self.push, [("u2", "1 inmueble(s) para Ana")])
        self.db["requerimientos_busqueda"][0]["ultima_alerta_en"] = None      # forzar otra vuelta
        self.assertEqual(asyncio.run(A.revisar_alertas()), 0)
        self.assertEqual(len(self.db["alertas_enviadas"]), 1)


if __name__ == "__main__":
    unittest.main()
