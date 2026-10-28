"""Comentarios urgentes de supervisión: quién puede crear, ver y dar por atendido."""
import asyncio
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

import routers.supervision as sup


ROOT = Path(__file__).resolve().parents[1]
ADMIN, AGENTE, OTRO = "u-admin", "u-agente", "u-otro"
ORG = "org-1"


def _ctx(rol, org=ORG):
    return {"org_id": org, "rol_org": rol, "activo": True, "org_tipo": "empresa"}


class _Base:
    """Simula PostgREST con unas pocas filas en memoria."""

    def __init__(self, contactos=None, actividades=None, miembros=None):
        self.contactos = contactos or []
        self.actividades = actividades or []
        self.miembros = miembros if miembros is not None else [
            {"org_id": ORG, "user_id": ADMIN}, {"org_id": ORG, "user_id": AGENTE}]
        self.creadas, self.parches, self.push = [], [], []

    async def get_rows(self, tabla, params, **_):
        if tabla == "contactos":
            ids = params["id"]
            return [c for c in self.contactos if ids == f"eq.{c['id']}" or ids.startswith("in.")]
        if tabla == "organizacion_miembros":
            return [m for m in self.miembros
                    if params["org_id"] == f"eq.{m['org_id']}" and params["user_id"] == f"eq.{m['user_id']}"]
        if tabla == "usuarios":
            return [{"id": ADMIN, "nombre": "Ana Admin"}, {"id": AGENTE, "nombre": "Beto Agente"}]
        if tabla == "actividades":
            filas = self.actividades
            if "id" in params:
                filas = [a for a in filas if params["id"] == f"eq.{a['id']}"]
            if "para_usuario" in params:
                op, val = params["para_usuario"].split(".", 1)
                filas = [a for a in filas if (a.get("para_usuario") == val) == (op == "eq")]
            return filas
        return []

    async def post_rows(self, tabla, fila, **_):
        self.creadas.append((tabla, fila))
        return [{**fila, "id": "act-nueva"}]

    async def patch_rows(self, tabla, params, payload, **_):
        self.parches.append((tabla, params, payload))
        return []


def _correr(base, usuario, ctx, coro_fn):
    async def push(*a, **k):
        base.push.append(a)
        return True

    with mock.patch.object(sup, "require_user_id", mock.AsyncMock(return_value=usuario)), \
         mock.patch.object(sup, "get_org_context", mock.AsyncMock(return_value=ctx)), \
         mock.patch.object(sup, "get_rows", base.get_rows), \
         mock.patch.object(sup, "post_rows", base.post_rows), \
         mock.patch.object(sup, "patch_rows", base.patch_rows), \
         mock.patch("push.enviar_push", push):
        return asyncio.run(coro_fn())


CLIENTE = {"id": "c1", "nombre": "Carla Cliente", "org_id": ORG, "user_id": ADMIN, "asignado_a": AGENTE}


class CrearTests(unittest.TestCase):
    def crear(self, base, usuario, ctx, **body):
        req = sup.ComentarioReq(**{"contacto_id": "c1", "texto": "Llámale hoy", **body})
        return _correr(base, usuario, ctx, lambda: sup.crear_comentario(req, None))

    def test_admin_crea_urgente_para_el_agente_asignado_y_le_avisa(self):
        base = _Base(contactos=[CLIENTE])
        res = self.crear(base, ADMIN, _ctx("admin"))
        self.assertTrue(res["ok"])
        tabla, fila = base.creadas[0]
        self.assertEqual(tabla, "actividades")
        self.assertEqual((fila["urgente"], fila["para_usuario"], fila["user_id"], fila["org_id"]),
                         (True, AGENTE, ADMIN, ORG))
        self.assertEqual(base.push[0][0], AGENTE)

    def test_un_agente_no_puede_crear_urgentes(self):
        base = _Base(contactos=[CLIENTE])
        with self.assertRaises(HTTPException) as e:
            self.crear(base, AGENTE, _ctx("agente"))
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(base.creadas, [])

    def test_cliente_de_otra_empresa_no(self):
        base = _Base(contactos=[{**CLIENTE, "org_id": "org-2"}])
        with self.assertRaises(HTTPException) as e:
            self.crear(base, ADMIN, _ctx("owner"))
        self.assertEqual(e.exception.status_code, 403)

    def test_sin_agente_o_para_uno_mismo_pide_asignar(self):
        base = _Base(contactos=[{**CLIENTE, "asignado_a": None}])
        with self.assertRaises(HTTPException) as e:
            self.crear(base, ADMIN, _ctx("owner"))
        self.assertEqual(e.exception.status_code, 400)

    def test_agente_que_ya_no_esta_activo(self):
        base = _Base(contactos=[CLIENTE], miembros=[{"org_id": ORG, "user_id": ADMIN}])
        with self.assertRaises(HTTPException) as e:
            self.crear(base, ADMIN, _ctx("owner"))
        self.assertEqual(e.exception.status_code, 400)

    def test_comentario_vacio(self):
        base = _Base(contactos=[CLIENTE])
        with self.assertRaises(HTTPException) as e:
            self.crear(base, ADMIN, _ctx("owner"), texto="   ")
        self.assertEqual(e.exception.status_code, 400)


PENDIENTE = {"id": "a1", "org_id": ORG, "urgente": True, "para_usuario": AGENTE,
             "user_id": ADMIN, "contacto_id": "c1", "texto": "Llámale", "atendido_en": None}


class AtendidoTests(unittest.TestCase):
    def marcar(self, base, usuario, ctx):
        return _correr(base, usuario, ctx, lambda: sup.marcar_atendido("a1", None))

    def test_el_agente_destinatario_lo_marca(self):
        base = _Base(actividades=[dict(PENDIENTE)])
        self.assertTrue(self.marcar(base, AGENTE, _ctx("agente"))["ok"])
        _, params, payload = base.parches[0]
        self.assertEqual(params["atendido_en"], "is.null")
        self.assertEqual(payload["atendido_por"], AGENTE)

    def test_un_admin_de_la_misma_empresa_tambien(self):
        base = _Base(actividades=[dict(PENDIENTE)])
        self.assertTrue(self.marcar(base, ADMIN, _ctx("admin"))["ok"])

    def test_otro_agente_no(self):
        base = _Base(actividades=[dict(PENDIENTE)])
        with self.assertRaises(HTTPException) as e:
            self.marcar(base, OTRO, _ctx("agente"))
        self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(base.parches, [])

    def test_admin_de_otra_empresa_no(self):
        base = _Base(actividades=[dict(PENDIENTE)])
        with self.assertRaises(HTTPException):
            self.marcar(base, OTRO, _ctx("owner", org="org-2"))

    def test_una_nota_normal_no_se_marca(self):
        base = _Base(actividades=[{**PENDIENTE, "urgente": False}])
        with self.assertRaises(HTTPException) as e:
            self.marcar(base, AGENTE, _ctx("agente"))
        self.assertEqual(e.exception.status_code, 404)


class PendientesTests(unittest.TestCase):
    def test_agente_ve_solo_los_suyos_y_supervisor_los_del_equipo(self):
        otro = {**PENDIENTE, "id": "a2", "para_usuario": OTRO}
        base = _Base(contactos=[CLIENTE], actividades=[dict(PENDIENTE), otro])
        res = _correr(base, AGENTE, _ctx("agente"), lambda: sup.listar_pendientes(None))
        self.assertEqual([c["id"] for c in res["para_mi"]], ["a1"])
        self.assertEqual(res["del_equipo"], [])
        self.assertEqual(res["para_mi"][0]["autor"], "Ana Admin")

        res = _correr(base, ADMIN, _ctx("owner"), lambda: sup.listar_pendientes(None))
        self.assertEqual(res["para_mi"], [])
        self.assertEqual(sorted(c["id"] for c in res["del_equipo"]), ["a1", "a2"])

    def test_sin_migracion_no_truena(self):
        async def falla(*a, **k):
            raise RuntimeError("column actividades.urgente does not exist")
        base = _Base()
        base.get_rows = falla
        res = _correr(base, AGENTE, _ctx("agente"), lambda: sup.listar_pendientes(None))
        self.assertFalse(res["activo"])
        res = _correr(base, AGENTE, _ctx("agente"), lambda: sup.contar_pendientes(None))
        self.assertEqual(res["pendientes"], 0)


class CableadoTests(unittest.TestCase):
    def test_router_registrado_y_migracion_con_candado(self):
        self.assertIn("app.include_router(supervision_router)", (ROOT / "main.py").read_text())
        sql = (ROOT / "sql-manual/20261013-supervision-urgente.sql").read_text()
        self.assertIn("create trigger actividades_candado_supervision", sql)
        self.assertTrue((ROOT / "sql-manual/20261013-supervision-urgente-REVERSA.sql").exists())


if __name__ == "__main__":
    unittest.main()
