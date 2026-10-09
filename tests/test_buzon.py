"""Buzón: reglas de asignación y registro de leads sin duplicar."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest import mock

import core.buzon as B


class AsignacionTests(unittest.TestCase):
    def test_manual_no_asigna(self):
        self.assertEqual(B.elegir_asignado({"modo": "manual"}, ["a"], None, [], datetime(2026, 10, 5, 10)), (None, None))

    def test_ruleta_rota_y_salta_inactivos(self):
        regla = {"modo": "ruleta", "ruleta_usuarios": ["a", "b", "c"], "ruleta_ultimo": 0}
        self.assertEqual(B.elegir_asignado(regla, ["a", "b", "c"], None, [], datetime.now()), ("b", 1))
        regla["ruleta_ultimo"] = 1
        self.assertEqual(B.elegir_asignado(regla, ["a", "c"], None, [], datetime.now()), ("a", 0))

    def test_agente_del_inmueble(self):
        regla = {"modo": "agente_inmueble"}
        self.assertEqual(B.elegir_asignado(regla, ["a", "b"], {"asignado_a": "b", "user_id": "a"}, [], datetime.now())[0], "b")
        self.assertEqual(B.elegir_asignado(regla, ["a"], {"asignado_a": "zz", "user_id": "a"}, [], datetime.now())[0], "a")
        self.assertEqual(B.elegir_asignado(regla, ["a"], None, [], datetime.now())[0], None)

    def test_guardias_por_dia_y_hora(self):
        # 2026-10-05 es lunes → dia=1
        guardias = [{"user_id": "a", "dia": 1, "hora_inicio": "09:00", "hora_fin": "14:00"},
                    {"user_id": "b", "dia": 1, "hora_inicio": "14:00:00", "hora_fin": "20:00:00"},
                    {"user_id": "c", "dia": 0, "hora_inicio": "22:00", "hora_fin": "06:00"}]
        regla = {"modo": "guardias", "ruleta_ultimo": -1}
        self.assertEqual(B.elegir_asignado(regla, ["a", "b", "c"], None, guardias, datetime(2026, 10, 5, 10, 30))[0], "a")
        self.assertEqual(B.elegir_asignado(regla, ["a", "b", "c"], None, guardias, datetime(2026, 10, 5, 18))[0], "b")
        self.assertEqual(B.elegir_asignado(regla, ["a", "b", "c"], None, guardias, datetime(2026, 10, 5, 21))[0], None)
        # domingo 23:30 → guardia que cruza la medianoche
        self.assertEqual(B.elegir_asignado(regla, ["c"], None, guardias, datetime(2026, 10, 4, 23, 30))[0], "c")


class RegistroTests(unittest.TestCase):
    def setUp(self):
        self.db = {"buzon_leads": [], "contactos": [], "propiedades": [{"id": "p" * 36, "org_id": "o1", "user_id": "u1", "asignado_a": None}]}
        self.push = []

        async def get_rows(t, params, timeout=None):
            filas = self.db.get(t, [])
            out = []
            for f in filas:
                ok = True
                for k, v in params.items():
                    if k in ("select", "limit", "order"):
                        continue
                    if v.startswith("eq.") and str(f.get(k)) != v[3:]:
                        ok = False
                if ok:
                    out.append(f)
            return out

        async def post_rows(t, fila, prefer=None, timeout=None):
            fila = dict(fila)
            fila.setdefault("id", f"{t}-{len(self.db.setdefault(t, [])) + 1}")
            self.db[t].append(fila)
            return [fila]

        async def patch_rows(t, params, cambios, prefer=None, timeout=None):
            out = []
            for f in self.db.get(t, []):
                if all(str(f.get(k)) == v[3:] for k, v in params.items() if v.startswith("eq.")):
                    f.update(cambios)
                    out.append(f)
            return out

        async def rpc(nombre, payload, timeout=None):
            return None

        async def fuente(org, nombre):
            return {"id": "f1", "nombre": nombre}

        async def asignar(org, prop):
            return "u2"

        async def avisar(uid, lead):
            self.push.append(uid)

        self.parches = [mock.patch.object(B, n, f) for n, f in (
            ("get_rows", get_rows), ("post_rows", post_rows), ("patch_rows", patch_rows),
            ("call_service_rpc", rpc), ("_fuente", fuente), ("asignar_automatico", asignar), ("avisar_asignacion", avisar))]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_lead_nuevo_crea_contacto_asigna_y_avisa(self):
        lead = asyncio.run(B.registrar_lead(org_id="o1", user_id="u1", canal="sitio", nombre="Ana",
                                            telefono="4431234567", propiedad_id="p" * 36))
        self.assertEqual(lead["asignado_a"], "u2")
        self.assertEqual(lead["fuente"], "Sitio web")
        self.assertEqual(len(self.db["contactos"]), 1)
        self.assertEqual(self.db["contactos"][0]["nombre"], "ANA")
        self.assertEqual(self.push, ["u2"])

    def test_misma_conversacion_no_duplica_y_reabre(self):
        a = asyncio.run(B.registrar_lead(org_id="o1", user_id="u1", canal="whatsapp", nombre="Ana", referencia="conv1"))
        self.db["buzon_leads"][0]["estado"] = "atendida"
        b = asyncio.run(B.registrar_lead(org_id="o1", user_id="u1", canal="whatsapp", mensaje="hola otra vez", referencia="conv1"))
        self.assertEqual(len(self.db["buzon_leads"]), 1)
        self.assertEqual(b["id"], a["id"])
        self.assertEqual(b["estado"], "sin_atender")

    def test_inmueble_de_otra_organizacion_no_se_liga(self):
        self.db["propiedades"][0]["org_id"] = "otra"
        lead = asyncio.run(B.registrar_lead(org_id="o1", user_id="u1", canal="manual", nombre="X", telefono="4431112222",
                                            propiedad_id="p" * 36))
        self.assertIsNone(lead["propiedad_id"])


if __name__ == "__main__":
    unittest.main()
