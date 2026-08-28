from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

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


def create_import_all_router(get_context: Callable[[], dict[str, Any]]) -> APIRouter:
    """Create the legacy bulk-property import route without mounting it early.

    During the prepared state only ``router`` is mounted by main.py, so this
    factory cannot duplicate ``POST /easybroker/import-all``. The bounded AST
    transform mounts this router only after removing the legacy @app route.
    Dependencies are resolved on every request to preserve main.py's mutable
    compatibility/test seams exactly during progressive decomposition.
    """
    import_all_router = APIRouter()

    @import_all_router.post("/easybroker/import-all")
    async def easybroker_import_all(request: Request):
        deps = get_context()
        get_user_id_from_token_dep = deps["get_user_id_from_token"]
        get_eb_key_for_user_dep = deps["get_eb_key_for_user"]
        supabase_url = deps["SUPABASE_URL"]
        supabase_service_key = deps["SUPABASE_SERVICE_KEY"]
        eb_status_map = deps["_EB_STATUS_MAP"]
        eb_status_default = deps["_EB_STATUS_DEFAULT"]
        eb_limite_propiedades = deps["_EB_LIMITE_PROPIEDADES"]
        get_rows_dep = deps["get_rows"]
        eb_get_reintentos = deps["_eb_get_reintentos"]
        eb_base = deps["EB_BASE"]
        eb_headers_dep = deps["eb_headers"]
        get_org_id_for_user_dep = deps["get_org_id_for_user"]
        eb_to_brokr = deps["_eb_to_brokr"]
        eb_lote = deps["_EB_LOTE"]
        eb_pausa_lote = deps["_EB_PAUSA_LOTE"]
        prog = deps["_prog"]
        upsert_rows_dep = deps["upsert_rows"]
        migrar_fotos_org = deps["_migrar_fotos_org"]
        httpx_dep = deps["httpx"]
        asyncio_dep = deps["asyncio"]
        time_dep = deps["time"]

        user_id = await get_user_id_from_token_dep(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
        user_key = await get_eb_key_for_user_dep(user_id)
        if not user_key:
            raise HTTPException(status_code=400, detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker antes de importar.")
        if not supabase_url or not supabase_service_key:
            raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

        try:
            body_imp = await request.json()
        except Exception:
            body_imp = {}
        fotos_diferidas = bool((body_imp or {}).get("fotos_diferidas"))
        pedidos = (body_imp or {}).get("statuses")
        if isinstance(pedidos, str):
            pedidos = [pedidos]
        if isinstance(pedidos, list):
            statuses_elegidos = [s for s in eb_status_map if s in pedidos]
        else:
            statuses_elegidos = []
        if not statuses_elegidos:
            statuses_elegidos = list(eb_status_default)

        sb_headers = {
            "apikey": supabase_service_key,
            "Authorization": f"Bearer {supabase_service_key}",
            "Content-Type": "application/json",
        }
        _ = sb_headers  # Preserve the legacy construction in this behavior-only cut.

        existentes_por_eb_id = {}
        try:
            try:
                filas_existentes = await get_rows_dep(
                    "propiedades",
                    {"user_id": f"eq.{user_id}",
                     "eb_public_id": "not.is.null",
                     "select": "eb_public_id,notas,estatus"},
                    timeout=15,
                )
            except httpx_dep.HTTPStatusError:
                filas_existentes = []
            for row in filas_existentes:
                eb_id = row.get("eb_public_id")
                if eb_id:
                    existentes_por_eb_id[eb_id] = {
                        "notas": row.get("notas"),
                        "estatus": row.get("estatus"),
                    }
        except Exception as e:
            print(f"[import-all] Error leyendo existentes: {e}")

        estatus_por_pid = {}
        conteo_por_estatus = {}
        ids_published = []
        limite_alcanzado = False
        descartadas_estatus = 0
        for s in statuses_elegidos:
            conteo_por_estatus[s] = 0

        async with httpx_dep.AsyncClient(timeout=30) as client:
            for eb_status in statuses_elegidos:
                if limite_alcanzado:
                    break
                brokr_status = eb_status_map[eb_status]
                pagina = 1
                while pagina <= 400:
                    r = await eb_get_reintentos(
                        client,
                        f"{eb_base}/properties",
                        eb_headers_dep(user_key),
                        [("limit", 50), ("page", pagina),
                         ("search[statuses][]", eb_status)],
                        timeout=30.0,
                    )
                    if r is None:
                        break
                    if r.status_code == 401:
                        raise HTTPException(status_code=401, detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil.")
                    if r.status_code != 200:
                        break
                    data = r.json()
                    content = data.get("content", []) or []
                    if not content:
                        break
                    for p in content:
                        if len(ids_published) >= eb_limite_propiedades:
                            limite_alcanzado = True
                            break
                        pid = p.get("public_id")
                        if not pid:
                            continue
                        if pid in estatus_por_pid:
                            descartadas_estatus += 1
                            continue
                        estatus_por_pid[pid] = brokr_status
                        conteo_por_estatus[eb_status] = conteo_por_estatus.get(eb_status, 0) + 1
                        ids_published.append(pid)
                    if limite_alcanzado:
                        break
                    if not data.get("pagination", {}).get("next_page"):
                        break
                    pagina += 1

        total_eb = len(ids_published)
        errores: list = []
        inmuebles_listos: list = []

        org_id_import = await get_org_id_for_user_dep(user_id)
        if not org_id_import:
            raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")

        async def fetch_one(client, pid: str):
            try:
                rd = await eb_get_reintentos(
                    client,
                    f"{eb_base}/properties/{pid}",
                    eb_headers_dep(user_key),
                    timeout=20.0,
                )
                if rd is None:
                    return ("err", {"id": pid, "error": "EasyBroker no respondió tras varios intentos"})
                if rd.status_code != 200:
                    return ("err", {"id": pid, "error": f"EB status {rd.status_code}"})
                prop_full = rd.json()
                inmueble = eb_to_brokr(prop_full, user_id)
                inmueble["org_id"] = org_id_import
                eb_estatus = estatus_por_pid.get(pid)
                if eb_estatus:
                    inmueble["estatus"] = eb_estatus
                prev = existentes_por_eb_id.get(pid)
                if prev:
                    if prev.get("notas"):
                        inmueble["notas"] = prev["notas"]
                    if prev.get("estatus"):
                        inmueble["estatus"] = prev["estatus"]
                return ("ok", inmueble)
            except Exception as e:
                return ("err", {"id": pid, "error": str(e)[:120]})

        batch = eb_lote
        lotes_fallidos_seguidos = 0
        async with httpx_dep.AsyncClient(timeout=30) as client:
            for i in range(0, len(ids_published), batch):
                chunk = ids_published[i:i+batch]
                prog(user_id, f"propiedades {min(i + batch, len(ids_published))} de {len(ids_published)}")
                inicio_lote = time_dep.monotonic()
                results = await asyncio_dep.gather(*[fetch_one(client, pid) for pid in chunk])
                resto = eb_pausa_lote - (time_dep.monotonic() - inicio_lote)
                if resto > 0 and i + batch < len(ids_published):
                    await asyncio_dep.sleep(resto)
                fallos_lote = 0
                for status, payload in results:
                    if status == "ok":
                        inmuebles_listos.append(payload)
                    else:
                        errores.append(payload)
                        fallos_lote += 1
                lotes_fallidos_seguidos = (lotes_fallidos_seguidos + 1
                                           if fallos_lote == len(chunk) else 0)
                if lotes_fallidos_seguidos >= 4:
                    raise HTTPException(status_code=429, detail="EasyBroker está limitando las peticiones de tu cuenta (429 sostenido). Espera 10-15 minutos y vuelve a correr la migración: lo ya importado no se pierde ni se duplica.")

        upserted = 0
        upsert_batch = 50
        async with httpx_dep.AsyncClient(timeout=60) as client:
            _ = client  # Preserve legacy client lifetime although Core owns the upsert call.
            for i in range(0, len(inmuebles_listos), upsert_batch):
                chunk = inmuebles_listos[i:i+upsert_batch]
                ultimo_fallo = "sin respuesta"
                guardado = False
                for intento in range(3):
                    try:
                        await upsert_rows_dep(
                            "propiedades",
                            chunk,
                            conflict="org_id,eb_public_id",
                            prefer="resolution=merge-duplicates,return=minimal",
                            timeout=60,
                            accepted_statuses=(200, 201, 204),
                        )
                        upserted += len(chunk)
                        guardado = True
                        break
                    except httpx_dep.HTTPStatusError as e:
                        ultimo_fallo = f"Supabase {e.response.status_code}: {e.response.text[:200]}"
                    except Exception as e:
                        ultimo_fallo = str(e)[:200]
                    await asyncio_dep.sleep(1.5 * (2 ** intento))
                if not guardado:
                    errores.append({
                        "id": f"lote_{i // upsert_batch}",
                        "error": ultimo_fallo
                    })

        nuevas = sum(1 for inm in inmuebles_listos if inm["eb_public_id"] not in existentes_por_eb_id)
        actualizadas = upserted - nuevas if upserted >= nuevas else 0

        fotos_lanzado = False
        if org_id_import and upserted and not fotos_diferidas:
            try:
                asyncio_dep.create_task(migrar_fotos_org(org_id_import))
                fotos_lanzado = True
            except Exception as e:
                print(f"[import-all] No se pudo lanzar el guardado de fotos: {e}")

        return {
            "total_easybroker": total_eb,
            "importadas": nuevas,
            "actualizadas": actualizadas,
            "ya_existian": actualizadas,
            "por_estatus": conteo_por_estatus,
            "statuses": statuses_elegidos,
            "descartadas": descartadas_estatus,
            "limite": eb_limite_propiedades,
            "limite_alcanzado": limite_alcanzado,
            "fotos_en_proceso": fotos_lanzado,
            "errores": errores
        }

    return import_all_router
