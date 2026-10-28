"""PATCH /org/contactos/{id}: el agente asignado (o un compañero con "ver
contactos del equipo") puede guardar el formulario de un cliente que creó
otra persona, sin que el cliente cambie de dueño. Antes la base lo rechazaba
con "new row violates row-level security policy (USING expression)"."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from routers import organizaciones as org

ROOT = Path(__file__).resolve().parents[1]
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
            return [{"user_id": "yesi"}] if params["user_id"] == "eq.yesi" else []
        return [dict(self.c)] if self.c and params["id"] == f"eq.{self.c['id']}" else []

    async def patch(self, tabla, params, payload):
        self.patches.append(payload)
        if self.guarda:
            self.c.update(payload)


def _llamar(user, db, body, ctx=None):
    async def _uid(_r):
        return user

    async def _ctx(_u):
        return ctx

    with mock.patch.object(org, "get_user_id_from_token", _uid), \
         mock.patch.object(org, "get_org_context", _ctx), \
         mock.patch.object(org, "_sb_get", db.get), \
         mock.patch.object(org, "_sb_patch", db.patch):
        return asyncio.run(org.editar_contacto("c1", _Req(body)))


def _contacto(**kw):
    c = {"id": "c1", "user_id": "yesi", "org_id": ORG, "asignado_a": "yo",
         "notas": "", "updated_at": "2026-01-01T00:00:00+00:00"}
    c.update(kw)
    return c


def _ctx(rol="agente", permisos=None, org_id=ORG):
    return {"org_id": org_id, "rol_org": rol, "activo": True, "permisos": permisos or {}}


class EditarContactoTests(unittest.TestCase):
    def test_agente_asignado_guarda_notas_de_un_cliente_que_creo_otra(self):
        db = _Db(_contacto())
        sin_equipo = _ctx(permisos={"ver_contactos_equipo": False})
        self.assertTrue(_llamar("yo", db, {"notas": "Quiere 3 recámaras",
                                           "descripcion_privada": "Score 8"}, sin_equipo)["ok"])
        self.assertEqual(db.c["notas"], "Quiere 3 recámaras")
        self.assertEqual(db.c["user_id"], "yesi")

    def test_nunca_cambia_dueno_empresa_ni_asignado(self):
        db = _Db(_contacto())
        _llamar("yo", db, {"notas": "x", "user_id": "yo", "org_id": "org-2",
                           "asignado_a": "otro", "id": "c9"}, _ctx())
        self.assertEqual(set(db.patches[0]), {"notas", "updated_at"})

    def test_companero_con_ver_contactos_equipo_si_puede(self):
        db = _Db(_contacto(asignado_a="otro"))
        _llamar("yo", db, {"etiquetas": ["vip"], "es_potencial": True}, _ctx())
        self.assertEqual(db.c["etiquetas"], ["vip"])

    def test_sin_permiso_de_equipo_ni_asignado_no_puede(self):
        db = _Db(_contacto(asignado_a="otro"))
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"notas": "x"}, _ctx(permisos={"ver_contactos_equipo": False}))
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(db.patches, [])

    def test_otra_empresa_no_puede(self):
        db = _Db(_contacto(asignado_a=None))
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"notas": "x"}, _ctx("owner", org_id="org-2"))
        self.assertEqual(e.exception.status_code, 403)

    def test_tipos_invalidos_y_vacio(self):
        db = _Db(_contacto())
        for malo in ({"notas": 5}, {"etiquetas": "vip"}, {"es_potencial": "si"},
                     {"probabilidad": "altisima"}):
            with self.assertRaises(HTTPException) as e:
                _llamar("yo", db, malo, _ctx())
            self.assertEqual(e.exception.status_code, 400, malo)
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"user_id": "yo"}, _ctx())
        self.assertEqual(e.exception.status_code, 400)

    def test_si_no_se_guardo_no_dice_que_si(self):
        db = _Db(_contacto(), guarda=False)
        with self.assertRaises(HTTPException) as e:
            _llamar("yo", db, {"notas": "x"}, _ctx())
        self.assertEqual(e.exception.status_code, 500)

    def test_sin_sesion_401(self):
        with self.assertRaises(HTTPException) as e:
            _llamar(None, _Db(_contacto()), {"notas": "x"})
        self.assertEqual(e.exception.status_code, 401)


class FrontendTests(unittest.TestCase):
    def test_editar_ya_no_reenvia_el_dueno(self):
        comun = (ROOT / "ficha-comun.js").read_text()
        self.assertIn("async function bkGuardarContacto", comun)
        self.assertIn("['id', 'user_id', 'org_id', 'asignado_a', 'created_at'].forEach(k => delete campos[k])", comun)
        for pagina in ("clientes.html", "contactos.html"):
            html = (ROOT / pagina).read_text()
            self.assertIn("return bkGuardarContacto(contacto, _contactosMem.some(c => c.id === contacto.id));", html)


if __name__ == "__main__":
    unittest.main()
