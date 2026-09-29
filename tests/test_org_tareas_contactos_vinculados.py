"""POST /org/tareas/contactos-vinculados: el asesor al que le asignan una
tarea ligada al cliente de un compañero debe poder saber quién es ese cliente,
sin abrirle los demás clientes del compañero ni los de otra empresa."""
from __future__ import annotations

import asyncio
from unittest import mock
import unittest

from fastapi import HTTPException

from routers import organizaciones as org

YO = "u-yo"
COMPA = "u-compa"
OTRO = "u-otra-empresa"
ORG = "org-1"

TAREAS = [
    # Asignada a mí, cliente del compañero ligado por tareas_contactos.
    {"id": "t1", "org_id": ORG, "user_id": COMPA, "asignado_a": YO, "contacto_id": None},
    # Asignada a mí, vínculo viejo por columna.
    {"id": "t2", "org_id": ORG, "user_id": COMPA, "asignado_a": YO, "contacto_id": "c2"},
    # De la empresa pero NO asignada a mí ni creada por mí.
    {"id": "t3", "org_id": ORG, "user_id": COMPA, "asignado_a": COMPA, "contacto_id": "c3"},
]
VINCULOS = [
    {"tarea_id": "t1", "contacto_id": "c1"},
    {"tarea_id": "t1", "contacto_id": "cx"},   # cliente de otra empresa
    {"tarea_id": "t3", "contacto_id": "c3"},
]
CONTACTOS = {
    "c1": {"id": "c1", "nombre": "Ana", "telefono": "4431112222", "wa": None,
           "email": "a@x.com", "tipo": "comprador", "user_id": COMPA, "org_id": ORG},
    "c2": {"id": "c2", "nombre": "Beto", "telefono": None, "wa": "4433334444",
           "email": None, "tipo": "vendedor", "user_id": COMPA, "org_id": None},
    "c3": {"id": "c3", "nombre": "Oculto", "user_id": COMPA, "org_id": ORG},
    "cx": {"id": "cx", "nombre": "Ajeno", "user_id": OTRO, "org_id": "org-2"},
}


def _ids(param: str):
    return [x.strip('"') for x in param[len("in.("):-1].split(",")]


async def _fake_get(tabla, params):
    if tabla == "tareas":
        ids = _ids(params["id"])
        return [t for t in TAREAS if t["id"] in ids and params["org_id"] == f"eq.{t['org_id']}"]
    if tabla == "tareas_contactos":
        ids = _ids(params["tarea_id"])
        return [v for v in VINCULOS if v["tarea_id"] in ids]
    if tabla == "contactos":
        return [CONTACTOS[i] for i in _ids(params["id"]) if i in CONTACTOS]
    if tabla == "organizacion_miembros":
        return [{"user_id": YO}, {"user_id": COMPA}]
    return []


def _llamar(user, tarea_ids):
    async def _uid(_req):
        return user

    async def _ctx(_uid):
        return {"org_id": ORG} if user else None

    with mock.patch.object(org, "get_user_id_from_token", _uid), \
         mock.patch.object(org, "get_org_context", _ctx), \
         mock.patch.object(org, "_sb_get", _fake_get):
        return asyncio.run(org.contactos_de_mis_tareas(
            org.TareasContactosReq(tarea_ids=tarea_ids), request=None))


class ContactosDeMisTareasTests(unittest.TestCase):
    def test_devuelve_clientes_de_tareas_asignadas_a_mi(self):
        r = _llamar(YO, ["t1", "t2", "t3"])
        nombres = sorted(c["nombre"] for c in r["contactos"])
        self.assertEqual(nombres, ["Ana", "Beto"])

    def test_no_filtra_campos_internos(self):
        r = _llamar(YO, ["t1"])
        self.assertEqual(set(r["contactos"][0]),
                         {"id", "nombre", "telefono", "wa", "email", "tipo"})

    def test_no_abre_tareas_que_no_son_mias(self):
        self.assertEqual(_llamar(YO, ["t3"]), {"contactos": []})

    def test_no_abre_clientes_de_otra_empresa(self):
        nombres = [c["nombre"] for c in _llamar(YO, ["t1"])["contactos"]]
        self.assertNotIn("Ajeno", nombres)

    def test_ids_raros_se_ignoran(self):
        self.assertEqual(_llamar(YO, ['t1") or (1=1', ""]), {"contactos": []})

    def test_sin_sesion_da_401(self):
        with self.assertRaises(HTTPException) as e:
            _llamar(None, ["t1"])
        self.assertEqual(e.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
