"""Cifrado de tokens de WhatsApp: lectura doble, sin doble cifrado, sin llave = como antes."""
import asyncio
import unittest
from unittest import mock

from cryptography.fernet import Fernet

import core.whatsapp_secrets as ws
import routers.whatsapp_chatgpt as wac
import routers.whatsapp_data as wd
import routers.whatsapp_token_crypto as conv


LLAVE = ws._fernet_desde("llave-de-prueba-larga-1234567890")
OTRA = ws._fernet_desde("otra-llave-distinta-0987654321")


def correr(coro):
    return asyncio.run(coro)


class CifradoBasicoTests(unittest.TestCase):
    def test_ida_y_vuelta(self):
        c = ws.cifrar_token("EAAtoken123", fernet=LLAVE)
        self.assertTrue(c.startswith(ws.PREFIX))
        self.assertNotIn("EAAtoken123", c)
        self.assertEqual(ws.descifrar_token(c, fernet=LLAVE), "EAAtoken123")

    def test_token_viejo_en_texto_plano_se_lee_igual(self):
        self.assertEqual(ws.descifrar_token("EAAviejo", fernet=LLAVE), "EAAviejo")
        self.assertEqual(ws.descifrar_token("EAAviejo", fernet=None), "EAAviejo")

    def test_nunca_cifra_dos_veces(self):
        c = ws.cifrar_token("EAAx", fernet=LLAVE)
        self.assertEqual(ws.cifrar_token(c, fernet=LLAVE), c)

    def test_sin_llave_guarda_como_hoy(self):
        with mock.patch.object(ws, "_FERNET", None):
            self.assertEqual(ws.cifrar_token("EAAx"), "EAAx")
            self.assertEqual(ws.proteger_para_guardar("wa2_numeros", {"access_token": "EAAx"}),
                             {"access_token": "EAAx"})

    def test_llave_equivocada_no_truena(self):
        c = ws.cifrar_token("EAAx", fernet=LLAVE)
        self.assertEqual(ws.descifrar_token(c, fernet=OTRA), "")

    def test_vacios_y_no_texto(self):
        for v in (None, "", 0):
            self.assertEqual(ws.cifrar_token(v, fernet=LLAVE), v)

    def test_cualquier_texto_sirve_de_llave(self):
        self.assertIsInstance(ws._fernet_desde("x"), Fernet)
        self.assertIsNone(ws._fernet_desde("   "))

    def test_solo_tablas_con_token(self):
        with mock.patch.object(ws, "_FERNET", LLAVE):
            cuerpo = {"access_token": "EAAx"}
            self.assertEqual(ws.proteger_para_guardar("wa2_contactos", cuerpo), cuerpo)
            for tabla in ("wa2_numeros", "wac_numbers"):
                self.assertTrue(ws.proteger_para_guardar(tabla, cuerpo)["access_token"].startswith(ws.PREFIX))
            self.assertEqual(cuerpo, {"access_token": "EAAx"}, "no debe modificar el dict original")


class AdaptadoresTests(unittest.TestCase):
    def test_wa2_numeros_guarda_cifrado_y_lee_en_claro(self):
        guardado = {}

        async def post_rows(table, body, **kw):
            guardado.update(body)
            return [dict(body)]

        async def get_rows(table, params, **kw):
            return [dict(guardado), {"id": 2, "access_token": "EAAviejo"}]

        with mock.patch.object(ws, "_FERNET", LLAVE), \
             mock.patch.object(wd, "post_rows", post_rows), mock.patch.object(wd, "get_rows", get_rows):
            filas = correr(wd.sb_post("wa2_numeros", {"id": 1, "access_token": "EAAnuevo"}))
            self.assertEqual(filas[0]["access_token"], "EAAnuevo")
            self.assertTrue(guardado["access_token"].startswith(ws.PREFIX))
            leidas = correr(wd.sb_get("wa2_numeros", {}))
            self.assertEqual([f["access_token"] for f in leidas], ["EAAnuevo", "EAAviejo"])

    def test_wa2_numeros_patch_cifra(self):
        enviado = {}

        async def patch_rows(table, params, body, **kw):
            enviado.update(body)
            return [dict(body)]

        with mock.patch.object(ws, "_FERNET", LLAVE), mock.patch.object(wd, "patch_rows", patch_rows):
            filas = correr(wd.sb_patch("wa2_numeros", {"id": "eq.1"}, {"access_token": "EAAp"}))
            self.assertTrue(enviado["access_token"].startswith(ws.PREFIX))
            self.assertEqual(filas[0]["access_token"], "EAAp")

    def test_wac_numbers_tambien_queda_cubierto(self):
        guardado = {}

        async def upsert_rows(table, payload, **kw):
            guardado.update(payload)
            return [dict(payload)]

        async def get_rows(table, params, **kw):
            return [dict(guardado)]

        with mock.patch.object(ws, "_FERNET", LLAVE), \
             mock.patch.object(wac, "upsert_rows", upsert_rows), mock.patch.object(wac, "get_rows", get_rows):
            filas = correr(wac._sb_upsert("wac_numbers", {"phone_number_id": "1", "access_token": "EAAc"}, "phone_number_id"))
            self.assertTrue(guardado["access_token"].startswith(ws.PREFIX))
            self.assertEqual(filas[0]["access_token"], "EAAc")
            self.assertEqual(correr(wac._sb_get("wac_numbers", {}))[0]["access_token"], "EAAc")


class ConversionTests(unittest.TestCase):
    def _base(self, filas_por_tabla):
        parches = []

        async def get_rows(table, params, **kw):
            return [dict(f) for f in filas_por_tabla.get(table, [])]

        async def patch_rows(table, params, body, **kw):
            parches.append((table, dict(params), dict(body)))
            return [{}]

        return get_rows, patch_rows, parches

    def test_sin_llave_no_hace_nada(self):
        get_rows, patch_rows, parches = self._base({"wa2_numeros": [{"id": 1, "access_token": "EAAx"}]})
        with mock.patch.object(ws, "_FERNET", None), \
             mock.patch.object(conv, "get_rows", get_rows), mock.patch.object(conv, "patch_rows", patch_rows):
            self.assertEqual(correr(conv.convertir_tokens("cifrar")), {})
        self.assertEqual(parches, [])

    def test_cifra_solo_los_de_texto_plano_y_con_condicion(self):
        ya = ws.cifrar_token("EAAya", fernet=LLAVE)
        filas = {"wa2_numeros": [{"id": 1, "access_token": "EAAx"}, {"id": 2, "access_token": ya},
                                 {"id": 3, "access_token": None}],
                 "wac_numbers": [{"id": 9, "access_token": "EAAc"}]}
        get_rows, patch_rows, parches = self._base(filas)
        with mock.patch.object(ws, "_FERNET", LLAVE), \
             mock.patch.object(conv, "get_rows", get_rows), mock.patch.object(conv, "patch_rows", patch_rows):
            res = correr(conv.convertir_tokens("cifrar"))
        self.assertEqual(res, {"wa2_numeros": 1, "wac_numbers": 1})
        self.assertEqual({(t, p["id"]) for t, p, _ in parches}, {("wa2_numeros", "eq.1"), ("wac_numbers", "eq.9")})
        for _, params, body in parches:
            # Solo cambia si el token sigue igual: evita cifrar dos veces.
            self.assertTrue(params["access_token"].startswith("eq.EAA"))
            self.assertTrue(body["access_token"].startswith(ws.PREFIX))

    def test_descifrar_regresa_texto_plano(self):
        ya = ws.cifrar_token("EAAya", fernet=LLAVE)
        get_rows, patch_rows, parches = self._base({"wa2_numeros": [{"id": 2, "access_token": ya},
                                                                    {"id": 3, "access_token": "EAAplano"}]})
        with mock.patch.object(ws, "_FERNET", LLAVE), \
             mock.patch.object(conv, "get_rows", get_rows), mock.patch.object(conv, "patch_rows", patch_rows):
            correr(conv.convertir_tokens("descifrar"))
        self.assertEqual(parches, [("wa2_numeros", {"id": "eq.2", "access_token": f"eq.{ya}"}, {"access_token": "EAAya"})])

    def test_accion_invalida_no_hace_nada(self):
        get_rows, patch_rows, parches = self._base({"wa2_numeros": [{"id": 1, "access_token": "EAAx"}]})
        with mock.patch.object(ws, "_FERNET", LLAVE), \
             mock.patch.object(conv, "get_rows", get_rows), mock.patch.object(conv, "patch_rows", patch_rows):
            self.assertEqual(correr(conv.convertir_tokens("borrar")), {})
        self.assertEqual(parches, [])


if __name__ == "__main__":
    unittest.main()
