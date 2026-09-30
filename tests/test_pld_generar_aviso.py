"""«Generar aviso» de punta a punta con la base de datos simulada."""
from __future__ import annotations

import asyncio
import copy
from unittest import mock
import unittest

from fastapi import HTTPException

from routers import cumplimiento as c
from tests.test_pld_inm import CFG, EXP_FISICA, _op


class _R:
    headers = {}
    client = None


class GenerarAvisoTests(unittest.TestCase):
    def _generar(self, ops, cfg=None, falla_subida=False, periodo="2026-09"):
        self.posts, self.patches, self.subidas = [], [], []

        async def uid(_r):
            return "u1"

        async def config(_u):
            return dict(cfg if cfg is not None else CFG)

        async def get(tabla, params):
            if tabla == "pld_operaciones":
                return copy.deepcopy(ops)
            if tabla == "pld_expedientes":
                return [dict(EXP_FISICA, estatus="completo")]
            return []

        async def post(tabla, payload):
            self.posts.append((tabla, payload))
            return [dict(payload, id="aviso-1")]

        async def patch(tabla, params, payload):
            self.patches.append((tabla, params, payload))
            return [{}]

        async def subir(bucket, ruta, contenido, **k):
            if falla_subida:
                raise RuntimeError("storage caído")
            self.subidas.append((ruta, contenido))

        async def nada(*a, **k):
            return None

        with mock.patch.object(c, "_uid", uid), mock.patch.object(c, "_config", config), \
             mock.patch.object(c, "_sb_get", get), mock.patch.object(c, "_sb_post", post), \
             mock.patch.object(c, "_sb_patch", patch), mock.patch.object(c, "upload_object", subir), \
             mock.patch.object(c, "bitacora", nada):
            return asyncio.run(c.generar_aviso(_R(), c.AvisoIn(periodo=periodo)))

    def test_genera_valida_guarda_y_amarra_operaciones(self):
        r = self._generar([_op(genera_aviso=True)])
        self.assertTrue(r["validado"])
        self.assertEqual(c.validar_xsd(r["xml"]), [])
        self.assertEqual(self.posts[0][1]["formato"], "INM")
        self.assertEqual(len(self.subidas), 1)
        self.assertEqual(self.subidas[0][1].decode("utf-8"), r["xml"])
        estatus = [p[2].get("estatus") for p in self.patches if p[0] == "pld_avisos"]
        self.assertIn("generado", estatus)
        amarre = [p for p in self.patches if p[0] == "pld_operaciones"][0]
        self.assertEqual(amarre[2]["aviso_id"], "aviso-1")

    def test_si_faltan_datos_no_crea_nada(self):
        op = _op()
        op["aviso_datos"] = {}
        with self.assertRaises(HTTPException) as e:
            self._generar([op])
        self.assertEqual(e.exception.status_code, 422)
        self.assertIn("\n• ", e.exception.detail)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.subidas, [])

    def test_sin_rfc_del_sujeto_obligado(self):
        with self.assertRaises(HTTPException) as e:
            self._generar([_op()], cfg={})
        self.assertEqual(e.exception.status_code, 400)
        self.assertIn("RFC", e.exception.detail)

    def test_arrendamiento_no_bloquea_el_periodo(self):
        ops = [_op(), _op(id="4f1c2b9e-1234-4abc-9def-000000000002", tipo_operacion="arrendamiento")]
        r = self._generar(ops)
        self.assertEqual(r["num_operaciones"], 1)
        self.assertIn("fracción XV", r["excluidas"])

    def test_solo_arrendamiento_explica_por_que(self):
        with self.assertRaises(HTTPException) as e:
            self._generar([_op(tipo_operacion="arrendamiento")])
        self.assertEqual(e.exception.status_code, 400)
        self.assertIn("fracción XV", e.exception.detail)

    def test_sin_operaciones(self):
        with self.assertRaises(HTTPException) as e:
            self._generar([])
        self.assertIn("No hay operaciones", e.exception.detail)

    def test_si_falla_el_guardado_no_queda_borrador_colgado(self):
        with self.assertRaises(HTTPException):
            self._generar([_op()], falla_subida=True)
        self.assertEqual(self.patches[-1][2], {"estatus": "descartado"})
        self.assertFalse([p for p in self.patches if p[0] == "pld_operaciones"])

    def test_periodo_invalido(self):
        with self.assertRaises(HTTPException) as e:
            self._generar([_op()], periodo="09-2026")
        self.assertEqual(e.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
