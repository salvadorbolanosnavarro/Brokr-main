"""Ajustes de CRM: normalización, fusión de duplicados y permisos."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

import routers.crm as crm


class _Req:
    def __init__(self, body=None):
        self._b = body

    async def json(self):
        return self._b


class CrmPurosTests(unittest.TestCase):
    def test_tel10_normaliza_mexico(self):
        self.assertEqual(crm.tel10("+52 1 (443) 123-4567"), "4431234567")
        self.assertEqual(crm.tel10("044 443 123 4567"), "4431234567")
        self.assertEqual(crm.tel10("12345"), "")

    def test_normaliza_y_clave(self):
        self.assertEqual(crm.normaliza("  Referído  "), "referido")
        self.assertEqual(crm.clave_de("Basura / Spam"), "basura_spam")

    def test_combinar_suma_telefonos_correos_etiquetas_y_notas(self):
        a = {"id": "c1", "nombre": "ANA", "telefono": "4431234567", "email": "ana@x.mx",
             "etiquetas": ["vip"], "notas": "Busca casa", "empresa": ""}
        b = {"id": "c2", "nombre": "ANA P", "telefono": "+52 443 999 0000", "email": "ana2@x.mx",
             "etiquetas": ["credito", "vip"], "notas": "Tiene INFONAVIT", "empresa": "ACME", "es_potencial": True}
        c = crm.combinar_contactos(a, b)
        self.assertEqual(c["empresa"], "ACME")
        self.assertEqual([t["numero"] for t in c["telefonos"]], ["+52 443 999 0000"])
        self.assertEqual([x["correo"] for x in c["correos"]], ["ana2@x.mx"])
        self.assertEqual(c["etiquetas"], ["credito", "vip"])
        self.assertIn("Tiene INFONAVIT", c["notas"])
        self.assertTrue(c["es_potencial"])
        self.assertNotIn("nombre", c)


class CrmPermisosTests(unittest.TestCase):
    def setUp(self):
        self.rol = "agente"
        self.parches = []

        async def uid(request):
            return "u1"

        async def ctx(user_id):
            return {"org_id": "org1", "activo": True, "rol_org": self.rol}

        for n, f in (("get_user_id_from_token", uid), ("get_org_context", ctx)):
            p = mock.patch.object(crm, n, f)
            p.start()
            self.parches.append(p)

    def tearDown(self):
        for p in self.parches:
            p.stop()

    def test_agente_no_cambia_etapas(self):
        with self.assertRaises(HTTPException) as e:
            asyncio.run(crm.crear_etapa(crm.EtapaReq(nombre="Nueva"), _Req()))
        self.assertEqual(e.exception.status_code, 403)

    def test_fusion_rechaza_contacto_de_otra_organizacion(self):
        async def get_rows(tabla, params, timeout=None):
            if tabla == "contactos":
                return [{"id": "c1", "org_id": "org1", "user_id": "u1"}, {"id": "c2", "org_id": "org2", "user_id": "x"}]
            return [{"user_id": "u1"}]
        with mock.patch.object(crm, "get_rows", get_rows):
            with self.assertRaises(HTTPException) as e:
                asyncio.run(crm.fusionar_contactos(crm.FusionarReq(conservar_id="c1", eliminar_id="c2"), _Req()))
        self.assertEqual(e.exception.status_code, 404)

    def test_agente_no_asigna_en_lote(self):
        with self.assertRaises(HTTPException) as e:
            asyncio.run(crm.contactos_lote(crm.LoteContactosReq(ids=["c1"], asignado_a="u2"), _Req()))
        self.assertEqual(e.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
