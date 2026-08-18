import asyncio

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_rows
from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET
from routers.organizaciones import get_org_context


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key


async def _alcance_borrado(user_id: str):
    """Resolve the exact organization scope allowed by the legacy deletion rules."""
    ctx = await get_org_context(user_id)
    if not ctx:
        return (None, None)
    org_id = ctx.get("org_id")
    if not org_id:
        return (None, None)
    es_admin = ctx.get("rol_org") in ("owner", "admin")
    es_empresa = (ctx.get("org_tipo") or "personal") == "empresa"

    if es_empresa and not es_admin:
        return (None, None)
    return ({"org_id": f"eq.{org_id}"}, "empresa" if es_empresa else "personal")


_MSG_SIN_PERMISO = ("No tienes permiso para eliminar. En Broquer para Empresas solo "
                    "el dueño de la cuenta o un administrador puede eliminar registros. "
                    "Si necesitas quitar algo, pídeselo a quien administra tu cuenta.")


def _nombre_archivo_foto(url: str):
    """Extract a Broquer Storage object name from its public URL."""
    marca = f"/object/public/{_FOTOS_BUCKET}/"
    if isinstance(url, str) and marca in url:
        return url.split(marca, 1)[1].split("?")[0]
    return None


async def _borrar_fotos_storage(nombres: list):
    """Delete property-photo Storage objects in best-effort background batches."""
    if not nombres or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    borradas = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(nombres), 100):
                lote = nombres[i:i+100]
                try:
                    r = await client.request(
                        "DELETE",
                        f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}",
                        headers=sb_headers,
                        json={"prefixes": lote},
                    )
                    if r.status_code in (200, 204):
                        borradas += len(lote)
                except Exception:
                    pass
                await asyncio.sleep(0.2)
    finally:
        print(f"[borrado] {borradas} fotos eliminadas del almacenamiento")


@router.post("/propiedades/eliminar-masivo")
async def propiedades_eliminar_masivo(request: Request):
    """Delete selected or all in-scope properties, preserving legacy safeguards."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = (body or {}).get("ids") or []
    todos = bool((body or {}).get("todos"))
    if not todos and not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste ninguna propiedad.")
    if not todos and len(ids) > 2000:
        raise HTTPException(status_code=400, detail="Demasiadas propiedades a la vez. Hazlo en partes.")

    filtro, alcance = await _alcance_borrado(user_id)
    if not filtro:
        raise HTTPException(status_code=403, detail=_MSG_SIN_PERMISO)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    filas: list = []
    try:
        if todos:
            filas = await get_rows(
                "propiedades",
                {**filtro, "select": "id,fotos", "limit": "10000"},
                timeout=60,
            )
        else:
            for i in range(0, len(ids), 200):
                lote = ids[i:i+200]
                lista = ",".join(f'"{str(x)}"' for x in lote)
                filas.extend(await get_rows(
                    "propiedades",
                    {**filtro, "select": "id,fotos", "id": f"in.({lista})"},
                    timeout=60,
                ))
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")

    if not filas:
        return {"eliminadas": 0, "fotos_programadas": 0, "alcance": alcance}

    nombres = []
    for fila in filas:
        for f in (fila.get("fotos") or []):
            n = _nombre_archivo_foto(f)
            if n:
                nombres.append(n)

    ids_reales = [str(fila.get("id")) for fila in filas if fila.get("id")]
    eliminadas = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(ids_reales), 200):
                lote = ids_reales[i:i+200]
                lista = ",".join(f'"{x}"' for x in lote)
                try:
                    await delete_rows(
                        "propiedades",
                        {**filtro, "id": f"in.({lista})"},
                        prefer="return=minimal",
                        timeout=60,
                        accepted_statuses=(200, 204),
                    )
                    eliminadas += len(lote)
                except httpx.HTTPStatusError:
                    pass
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudieron borrar todas las propiedades.")

    if nombres:
        try:
            asyncio.create_task(_borrar_fotos_storage(nombres))
        except Exception:
            pass

    return {
        "eliminadas": eliminadas,
        "fotos_programadas": len(nombres),
        "alcance": alcance,
    }


@router.post("/contactos/eliminar-masivo")
async def contactos_eliminar_masivo(request: Request):
    """Delete selected or all in-scope contacts, preserving legacy safeguards."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = (body or {}).get("ids") or []
    todos = bool((body or {}).get("todos"))
    if not todos and not ids:
        raise HTTPException(status_code=400, detail="No seleccionaste ningún contacto.")

    filtro, alcance = await _alcance_borrado(user_id)
    if not filtro:
        raise HTTPException(status_code=403, detail=_MSG_SIN_PERMISO)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    filas: list = []
    try:
        if todos:
            filas = await get_rows(
                "contactos",
                {**filtro, "select": "id", "limit": "10000"},
                timeout=60,
            )
        else:
            for i in range(0, len(ids), 200):
                lote = ids[i:i+200]
                lista = ",".join(f'"{str(x)}"' for x in lote)
                filas.extend(await get_rows(
                    "contactos",
                    {**filtro, "select": "id", "id": f"in.({lista})"},
                    timeout=60,
                ))
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")

    ids_reales = [str(fila.get("id")) for fila in filas if fila.get("id")]
    if not ids_reales:
        return {"eliminados": 0, "alcance": alcance}

    eliminados = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(ids_reales), 200):
                lote = ids_reales[i:i+200]
                lista = ",".join(f'"{x}"' for x in lote)
                try:
                    await delete_rows(
                        "contactos",
                        {**filtro, "id": f"in.({lista})"},
                        prefer="return=minimal",
                        timeout=60,
                        accepted_statuses=(200, 204),
                    )
                    eliminados += len(lote)
                except httpx.HTTPStatusError:
                    pass
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudieron borrar todos los contactos.")

    return {"eliminados": eliminados, "alcance": alcance}
