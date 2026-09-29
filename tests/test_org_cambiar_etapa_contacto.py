"""PATCH /org/contactos/{id}/etapa: la etapa elegida en el pipeline se guarda
de verdad aunque el cliente sea de un compañero (antes RLS no actualizaba
nada, respondía 200 y la etapa "regresaba" al recargar)."""
from __future__ import annotations

import asyncio
from unittest import mock
import unittest

from fastapi import HTTPException

from routers import organizaciones as org

ORG = "org-1"


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class _Db:
    def __init__(self, contacto, guarda=True):
        self.c = contacto
        self.guarda = guarda
        self.patches = []

    async def get(self, tabla, params):
        if tabla == "organizacion_miembros":
            return [{"user_id": "compa"}] if params["user_id"] == "eq.compa" else []
        return [dict(self.c)] if self.c and params["id"] == f"eq.{self.c['id']}" else []

    async def patch(self, tabla, params, payload):
        self.patches.append(payload)
        if self.guarda:
            self.c.update({k: v for k, v in payload.items() if k != "updated_at"})


def _llamar(user, db, body, ctx=None, cid="c1"):
    async def _uid(_r):
        return user

    async def _ctx(_u):
        return ctx

    with mock.patch.object(org, "get_user_id_from_token", _uid), \
         mock.patch.object(org, "get_org_context", _ctx), \
         mock.patch.object(org, "_sb_get", db.get), \
         mock.patch.object(org, "_sb_patch", db.patch):
        return asyncio.run(org.cambiar_etapa_contacto(cid, _Req(body)))


def _contacto(**kw):
    c = {"id": "c1", "user_id": "compa", "org_id": ORG, "asignado_a": None,
         "estatus": "nuevo", "probabilidad": None}
    c.update(kw)
    return c


def _ctx(rol="agente", permisos=None, org_id=ORG):
    return {"org_id": org_id, "rol_org": rol, "activo": True, "permisos": permisos or {}}


class CambiarEtapaTests(unittest.TestCase):
    def test_companero_con_ver_contactos_equipo_descarta(self):
        db = _Db(_contacto())
        r = _llamar("yo", db, {"estatus": "Descartado"}, _ctx())
        self.assertEqual(r["estatus"], "descartado")
        self.assertEqual(db.c["estatus"], "descartado")

    def test_quitar_etapa(self):
        db = _Db(_contacto(estatus="activo"))
        _llamar("compa", db, {"estatus": None})
        self.assertIsNone(db.c["estatus"])

    def test_probabilidad(self):
        db = _Db(_contacto())
        _llamar("compa", db, {"probabilidad": "alta"})
        self.assertEqual(db.c["probabilidad"], "alta")
        with self.assertRaises(HTTPException) as e:
            _llamar("compa", db, {"probabilidad": "altisima"})
        self.assertEqual(e.exception.status_code, 400)

    def test_solo_toca_etapa_y_probabilidad(self):
        db = _Db(_contacto())
        _llamar("compa", db, {"estatus": "activo", "nombre": "X", "user_id": "yo"})
        self.assertEqual(set(db.patches[0]), {"estatus", "updated_at"})

    def test_sin_permiso_de_equipo_pero_asignado_si_puede(self):
        db = _Db(_contacto(asignado_a="yo"))
        _llamar("yo", db, {"estatus": "cerrado"}, _ctx(permisos={"ver_contactos_equipo": False}))
        self.assertEqual(db.c["estatus"], "cerrado")

    def test_sin_permiso_de_equipo_no_puede(self):
        db = _Db(_contacto())
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"estatus": "descartado"}, _ctx(permisos={"ver_contactos_equipo": False}))
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(db.patches, [])

    def test_otra_empresa_no_puede(self):
        db = _Db(_contacto())
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"estatus": "descartado"}, _ctx("owner", org_id="org-2"))
        self.assertEqual(e.exception.status_code, 403)

    def test_contacto_viejo_sin_org_de_un_companero(self):
        db = _Db(_contacto(org_id=None))
        _llamar("yo", db, {"estatus": "descartado"}, _ctx())
        self.assertEqual(db.c["estatus"], "descartado")

    def test_si_no_se_guardo_no_dice_que_si(self):
        db = _Db(_contacto(), guarda=False)
        with self.assertRaises(HTTPException) as e:
            _llamar("compa", db, {"estatus": "descartado"})
        self.assertEqual(e.exception.status_code, 500)

    def test_sin_sesion_401(self):
        with self.assertRaises(HTTPException) as e:
            _llamar(None, _Db(_contacto()), {"estatus": "x"})
        self.assertEqual(e.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
