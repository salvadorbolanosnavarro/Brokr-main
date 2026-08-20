from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.easybroker_migration import MIGRACIONES, PROGRESO_IMPORT, migration_key
from core.legacy_main_config import legacy_main_settings
from routers.organizaciones import get_org_id_for_user


router = APIRouter()


async def _job_migracion_eb(llave: str, auth_header: str):
    est = MIGRACIONES[llave]
    base = f"http://127.0.0.1:{legacy_main_settings.port}"
    pasos = [
        ("propiedades", "/easybroker/import-all", {"fotos_diferidas": True}),
        ("contactos", "/contactos/importar-eb", None),
        ("historial", "/easybroker/import-stats", None),
    ]
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            for idx, (nombre, ruta, body) in enumerate(pasos, start=1):
                est["paso"] = idx
                r = await client.post(
                    base + ruta,
                    headers={"Authorization": auth_header,
                             "Content-Type": "application/json"},
                    json=body if body is not None else {},
                )
                try:
                    d = r.json()
                except Exception:
                    d = {}
                if r.status_code != 200:
                    est["error"] = (d.get("detail")
                                    or f"Error {r.status_code} al importar {nombre}")
                    est["terminado"] = True
                    return
                est[nombre] = d
        est["terminado"] = True
    except Exception as e:
        est["error"] = f"El trabajo se interrumpió: {str(e)[:150]}"
        est["terminado"] = True


@router.post("/easybroker/migracion/iniciar")
async def migracion_eb_iniciar(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    llave = migration_key(org_id, user_id)

    previa = MIGRACIONES.get(llave)
    if previa and not previa.get("terminado") \
       and time.time() - previa.get("inicio", 0) < 1800:
        return {"ok": True, "en_curso": True}

    auth_header = request.headers.get("Authorization") or ""
    MIGRACIONES[llave] = {
        "paso": 1, "terminado": False, "error": None,
        "propiedades": None, "contactos": None, "historial": None,
        "inicio": time.time(),
    }
    asyncio.create_task(_job_migracion_eb(llave, auth_header))
    return {"ok": True, "en_curso": False}


@router.get("/easybroker/migracion/estado")
async def migracion_eb_estado(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    est = MIGRACIONES.get(migration_key(org_id, user_id))
    if not est:
        return {"ok": True, "existe": False}
    return {
        "ok": True, "existe": True,
        "detalle": PROGRESO_IMPORT.get(user_id),
        "paso": est["paso"],
        "terminado": est["terminado"],
        "error": est["error"],
        "propiedades": est["propiedades"],
        "contactos": est["contactos"],
        "historial": est["historial"],
    }
