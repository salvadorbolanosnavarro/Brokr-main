"""Reconectar un número que estaba en otra cuenta: misma empresa mueve, otra empresa archiva."""
import asyncio
import copy
import fnmatch
import itertools
import unittest
from pathlib import Path
from unittest import mock

import routers.whatsapp_number_owner as W


ROOT = Path(__file__).resolve().parents[1]
N = "num-1"
PNID = "123456"
VIEJO, NUEVO, COLEGA = "u-viejo", "u-nuevo", "u-colega"
_ids = itertools.count(1)


def _cumple(fila, params):
    for k, v in params.items():
        if k in ("select", "limit", "order"):
            continue
        op, _, val = v.partition(".")
        actual = fila.get(k)
        if op == "eq" and str(actual) != val:
            return False
        if op == "neq" and str(actual) == val:
            return False
        if op == "in" and str(actual) not in val.strip("()").split(","):
            return False
        if op == "like" and not fnmatch.fnmatch(str(actual), val):
            return False
    return True


class BaseFalsa:
    """PostgREST mínimo en memoria, con las reglas UNIQUE de producción."""

    def __init__(self, tablas):
        self.t = copy.deepcopy(tablas)
        self.fallar_en = None

    def _unicos(self, tabla):
        filas = self.t.get(tabla, [])
        reglas = {"wa2_contactos": ("numero_id", "wa_id"), "wa2_entrenamiento": ("user_id", "numero_id"),
                  "wa2_numeros": ("phone_number_id",), "wa2_conversaciones": ("contacto_id",)}
        if tabla in reglas:
            vistos = [tuple(f.get(c) for c in reglas[tabla]) for f in filas]
            if len(vistos) != len(set(vistos)):
                raise AssertionError(f"UNIQUE violado en {tabla}")

    async def get_rows(self, tabla, params, **kw):
        filas = [dict(f) for f in self.t.get(tabla, []) if _cumple(f, params)]
        if "limit" in params:
            filas = filas[: int(params["limit"])]
        return filas

    async def patch_rows(self, tabla, params, payload, **kw):
        if self.fallar_en == tabla:
            self.fallar_en = None
            raise RuntimeError("falla simulada")
        for f in self.t.get(tabla, []):
            if _cumple(f, params):
                f.update(payload)
        self._unicos(tabla)
        return []

    async def post_rows(self, tabla, body, **kw):
        fila = {"id": f"nuevo-{next(_ids)}", **body}
        self.t.setdefault(tabla, []).append(fila)
        self._unicos(tabla)
        return [dict(fila)]


def _datos(dueno_numero, dueno_historial):
    return {
        "wa2_numeros": [{"id": N, "user_id": dueno_numero, "phone_number_id": PNID, "display_number": "5213312965662",
                         "alias": "Mi línea", "access_token": "enc:wa1:xxx", "token_valido": True}],
        "wa2_contactos": [{"id": "k1", "user_id": dueno_historial, "numero_id": N, "wa_id": "5214433113974"}],
        "wa2_conversaciones": [{"id": "c1", "user_id": dueno_historial, "numero_id": N, "contacto_id": "k1"}],
        "wa2_mensajes": [{"id": "m1", "user_id": dueno_historial, "conversacion_id": "c1"},
                         {"id": "m2", "user_id": dueno_historial, "conversacion_id": "c1"}],
        "wa2_flujo_estados": [{"id": "f1", "user_id": dueno_historial, "conversacion_id": "c1"}],
        "wa2_citas": [{"id": "ci1", "user_id": dueno_historial, "numero_id": N}],
        "wa2_agenda": [{"id": "a1", "user_id": dueno_historial, "numero_id": N, "telefono": "5214433113974"}],
        "wa2_campanas": [{"id": "ca1", "user_id": dueno_historial, "numero_id": N}],
        "wa2_campana_envios": [{"id": "e1", "user_id": dueno_historial, "campana_id": "ca1"}],
        "wa2_automatizaciones": [{"id": "au1", "user_id": dueno_historial, "numero_id": N}],
        "wa2_entrenamiento": [{"id": "en1", "user_id": dueno_historial, "numero_id": N}],
        "organizacion_miembros": [
            {"user_id": NUEVO, "org_id": "org-A", "activo": True},
            {"user_id": COLEGA, "org_id": "org-A", "activo": False},   # ya salió de la empresa
            {"user_id": VIEJO, "org_id": "org-B", "activo": True},
        ],
    }


def _correr(db, nuevo=NUEVO, org_nuevo="org-A"):
    with mock.patch.object(W, "get_rows", db.get_rows), mock.patch.object(W, "patch_rows", db.patch_rows), \
         mock.patch.object(W, "post_rows", db.post_rows), \
         mock.patch.object(W, "get_org_id_for_user", mock.AsyncMock(return_value=org_nuevo)):
        asyncio.run(W.preparar_cambio_de_dueno(PNID, nuevo, "2026-10-09T06:00:00+00:00"))


def _duenos(db, tabla):
    return {f["user_id"] for f in db.t[tabla]}


class CambioDeDuenoTests(unittest.TestCase):
    def test_numero_nuevo_no_hace_nada(self):
        db = BaseFalsa({"wa2_numeros": []})
        _correr(db)
        self.assertEqual(db.t["wa2_numeros"], [])

    def test_mismo_dueno_no_hace_nada(self):
        db = BaseFalsa(_datos(NUEVO, NUEVO))
        antes = copy.deepcopy(db.t)
        _correr(db)
        self.assertEqual(db.t, antes)

    def test_misma_empresa_aunque_ya_salio_pasa_todo_al_nuevo(self):
        db = BaseFalsa(_datos(COLEGA, COLEGA))
        _correr(db)
        for tabla in W.TABLAS_POR_NUMERO + W.TABLAS_POR_CONVERSACION + ("wa2_campana_envios",):
            self.assertEqual(_duenos(db, tabla), {NUEVO}, tabla)
        self.assertEqual(len(db.t["wa2_numeros"]), 1, "no crea copia desconectada")

    def test_otra_empresa_se_queda_con_su_historial_en_copia_desconectada(self):
        db = BaseFalsa(_datos(VIEJO, VIEJO))
        _correr(db)
        copia = [n for n in db.t["wa2_numeros"] if n["id"] != N]
        self.assertEqual(len(copia), 1)
        copia = copia[0]
        self.assertEqual(copia["user_id"], VIEJO)
        self.assertTrue(copia["phone_number_id"].startswith(PNID + W.SUFIJO_ARCHIVADO))
        self.assertIsNone(copia["access_token"])
        self.assertFalse(copia["ia_enabled"])
        self.assertFalse(copia["token_valido"])
        self.assertTrue(copia["alias"].endswith("(desconectado)"))
        for tabla in W.TABLAS_POR_NUMERO:
            for fila in db.t[tabla]:
                self.assertEqual((fila["user_id"], fila["numero_id"]), (VIEJO, copia["id"]), tabla)
        # Mensajes y flujos no cambian de dueño: siguen con su conversación.
        self.assertEqual(_duenos(db, "wa2_mensajes"), {VIEJO})
        # El número real queda libre para que el nuevo dueño empiece de cero.
        self.assertEqual(db.t["wa2_contactos"][0]["numero_id"], copia["id"])

    def test_caso_real_numero_ya_reconectado_pero_historial_de_otra_cuenta(self):
        # Lo que pasó con demo@broquer.app: el número ya es del nuevo dueño
        # y las conversaciones siguen a nombre de la cuenta anterior.
        db = BaseFalsa(_datos(NUEVO, VIEJO))
        _correr(db)
        self.assertFalse(any(f["numero_id"] == N for f in db.t["wa2_contactos"]),
                         "el contacto viejo ya no estorba al nuevo dueño")
        copia = next(n for n in db.t["wa2_numeros"] if n["id"] != N)
        self.assertEqual(copia["user_id"], VIEJO)

    def test_dueno_anterior_sin_historial_no_crea_copia(self):
        db = BaseFalsa(_datos(VIEJO, VIEJO))
        for tabla in W.TABLAS_POR_NUMERO:
            db.t[tabla] = []
        _correr(db)
        self.assertEqual(len(db.t["wa2_numeros"]), 1)

    def test_nuevo_sin_empresa_archiva(self):
        db = BaseFalsa(_datos(COLEGA, COLEGA))
        _correr(db, org_nuevo=None)
        self.assertEqual(len(db.t["wa2_numeros"]), 2)
        self.assertEqual(_duenos(db, "wa2_contactos"), {COLEGA})

    def test_respeta_entrenamiento_propio_del_nuevo(self):
        db = BaseFalsa(_datos(COLEGA, COLEGA))
        db.t["wa2_entrenamiento"].append({"id": "en-propio", "user_id": NUEVO, "numero_id": N})
        _correr(db)  # no debe violar UNIQUE (user_id, numero_id)
        self.assertEqual(_duenos(db, "wa2_contactos"), {NUEVO})

    def test_si_falla_a_medias_reintentar_termina_el_trabajo(self):
        for caso in ((COLEGA, "wa2_contactos"), (VIEJO, "wa2_conversaciones")):
            anterior, tabla_que_falla = caso
            db = BaseFalsa(_datos(anterior, anterior))
            db.fallar_en = tabla_que_falla
            with self.assertRaises(W.HTTPException) as cm:
                _correr(db)
            self.assertEqual(cm.exception.status_code, 500)
            _correr(db)  # el usuario vuelve a conectar
            if anterior == COLEGA:
                for tabla in W.TABLAS_POR_NUMERO + W.TABLAS_POR_CONVERSACION + ("wa2_campana_envios",):
                    self.assertEqual(_duenos(db, tabla), {NUEVO}, tabla)
            else:
                copias = [n for n in db.t["wa2_numeros"] if n["id"] != N]
                self.assertEqual(len(copias), 1, "no duplica la copia desconectada")
                self.assertFalse(any(f.get("numero_id") == N for t in W.TABLAS_POR_NUMERO for f in db.t[t]))


class CableadoTests(unittest.TestCase):
    def test_los_dos_flujos_de_conexion_lo_llaman_antes_de_guardar(self):
        for archivo in ("whatsapp_connect_api.py", "whatsapp_connection.py"):
            src = (ROOT / "routers" / archivo).read_text(encoding="utf-8")
            llamada = src.index("await preparar_cambio_de_dueno(phone_number_id, user_id, _now())")
            guardado = src.index('existing = await sb_get("wa2_numeros", {"phone_number_id"')
            self.assertLess(llamada, guardado, archivo)


if __name__ == "__main__":
    unittest.main()
