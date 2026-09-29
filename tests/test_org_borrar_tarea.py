"""DELETE /org/tareas/{id}: borrar una tarea del equipo de verdad (antes RLS
la dejaba "borrada" en pantalla y reaparecía al recargar)."""
from __future__ import annotations

import asyncio
from unittest import mock
import unittest

from fastapi import HTTPException

from routers import organizaciones as org

ORG = "org-1"


class _Db:
    def __init__(self, tarea, borra=True):
        self.tarea = tarea
        self.borra = borra
        self.borrados = []

    async def get(self, tabla, params):
        return [self.tarea] if self.tarea and params["id"] == f"eq.{self.tarea['id']}" else []

    async def delete(self, tabla, params, **_):
        self.borrados.append((tabla, params))
        if self.borra:
            self.tarea = None


def _llamar(user, db, ctx=None, tarea_id="t1"):
    async def _uid(_req):
        return user

    async def _ctx(_uid):
        return ctx

    with mock.patch.object(org, "get_user_id_from_token", _uid), \
         mock.patch.object(org, "get_org_context", _ctx), \
         mock.patch.object(org, "_sb_get", db.get), \
         mock.patch.object(org, "delete_rows", db.delete):
        return asyncio.run(org.borrar_tarea(tarea_id, request=None))


def _tarea(**kw):
    t = {"id": "t1", "user_id": "creador", "org_id": ORG, "asignado_a": None}
    t.update(kw)
    return t


def _miembro(rol="agente", org_id=ORG):
    return {"org_id": org_id, "rol_org": rol, "activo": True}


class BorrarTareaTests(unittest.TestCase):
    def test_creador_borra(self):
        db = _Db(_tarea())
        self.assertEqual(_llamar("creador", db), {"ok": True})
        self.assertEqual(db.borrados, [("tareas", {"id": "eq.t1"})])

    def test_asignado_borra_tarea_de_un_companero(self):
        db = _Db(_tarea(asignado_a="yo"))
        self.assertEqual(_llamar("yo", db, _miembro()), {"ok": True})

    def test_admin_borra(self):
        db = _Db(_tarea())
        self.assertEqual(_llamar("jefe", db, _miembro("admin")), {"ok": True})

    def test_companero_sin_relacion_no_borra(self):
        db = _Db(_tarea(asignado_a="otro"))
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, _miembro())
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(db.borrados, [])

    def test_admin_de_otra_empresa_no_borra(self):
        db = _Db(_tarea())
        with self.assertRaises(HTTPException) as e:
            _llamar("jefe", db, _miembro("owner", "org-2"))
        self.assertEqual(e.exception.status_code, 403)

    def test_si_no_se_borro_no_dice_que_si(self):
        db = _Db(_tarea(), borra=False)
        with self.assertRaises(HTTPException) as e:
            _llamar("creador", db)
        self.assertEqual(e.exception.status_code, 500)

    def test_ya_no_existia_es_exito(self):
        self.assertTrue(_llamar("yo", _Db(None))["ok"])

    def test_sin_sesion_401(self):
        with self.assertRaises(HTTPException) as e:
            _llamar(None, _Db(_tarea()))
        self.assertEqual(e.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
