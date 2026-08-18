import asyncio
import io
import uuid as _uuid

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows, patch_rows
from core.property_photos import (
    FOTOS_BUCKET as _FOTOS_BUCKET,
    foto_migrable as _foto_migrable,
    fotos_en_proceso as _fotos_en_proceso,
)
from routers.organizaciones import get_org_id_for_user


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key

_EXT_POR_MIME = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
    "image/webp": "webp", "image/gif": "gif", "image/heic": "heic",
}
_FOTO_MAX_LADO = 1600
_FOTO_CALIDAD = 82


def _comprimir_imagen(raw: bytes):
    """Compress a migrated property image without changing the legacy fallback."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((_FOTO_MAX_LADO, _FOTO_MAX_LADO), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=_FOTO_CALIDAD,
                optimize=True, progressive=True)
        datos = buf.getvalue()
        if datos and len(datos) < len(raw):
            return (datos, "image/jpeg", "jpg")
    except Exception:
        pass
    return (None, None, None)


async def _foto_a_storage(client: httpx.AsyncClient, url: str, sb_headers: dict):
    """Download, compress and store one external property photo."""
    try:
        rd = await client.get(url, timeout=30.0, follow_redirects=True)
        if rd.status_code != 200 or not rd.content:
            return None
        mime = (rd.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
        raw = rd.content
    except Exception:
        return None

    ext = _EXT_POR_MIME.get(mime, "jpg")
    comp, mime_c, ext_c = await asyncio.to_thread(_comprimir_imagen, raw)
    if comp:
        raw, mime, ext = comp, mime_c, ext_c

    nombre = f"{_uuid.uuid4().hex}.{ext}"
    try:
        ru = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}",
            headers={**sb_headers, "Content-Type": mime},
            content=raw, timeout=60.0,
        )
    except Exception:
        return None
    if ru.status_code not in (200, 201):
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{_FOTOS_BUCKET}/{nombre}"


async def _migrar_fotos_org(org_id: str):
    """Recorre todas las propiedades de la empresa y guarda sus fotos externas."""
    if not org_id or org_id in _fotos_en_proceso:
        return
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    _fotos_en_proceso.add(org_id)
    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    cursor = None
    total_fotos = 0
    total_props = 0
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                params = {
                    "org_id": f"eq.{org_id}",
                    "select": "id,fotos",
                    "order": "id.asc",
                    "limit": "10",
                }
                if cursor:
                    params["id"] = f"gt.{cursor}"
                try:
                    filas = await get_rows("propiedades", params, timeout=30.0)
                except Exception:
                    break
                if not filas:
                    break

                for fila in filas:
                    cursor = fila.get("id")
                    fotos = fila.get("fotos") or []
                    if not isinstance(fotos, list) or not any(_foto_migrable(f) for f in fotos):
                        continue
                    nuevas = []
                    subidas = 0
                    for f in fotos:
                        if not _foto_migrable(f):
                            nuevas.append(f)
                            continue
                        nueva = await _foto_a_storage(client, f, sb_headers)
                        if nueva:
                            nuevas.append(nueva)
                            subidas += 1
                        else:
                            nuevas.append(f)
                    if not subidas:
                        continue
                    try:
                        try:
                            await patch_rows(
                                "propiedades",
                                {"id": f"eq.{fila.get('id')}"},
                                {"fotos": nuevas},
                                timeout=30.0,
                            )
                        except httpx.HTTPStatusError:
                            pass
                        total_props += 1
                        total_fotos += subidas
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)
    except Exception as e:
        print(f"[fotos] Error en segundo plano para org {org_id}: {e}")
    finally:
        _fotos_en_proceso.discard(org_id)
        print(f"[fotos] org {org_id}: {total_fotos} fotos guardadas en {total_props} propiedades")


@router.get("/easybroker/fotos-pendientes")
async def easybroker_fotos_pendientes(request: Request):
    """Cuántas propiedades de la empresa siguen con fotos fuera de Broquer."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return {"pendientes": 0, "en_proceso": False}
    pendientes = 0
    try:
        filas_pendientes = await get_rows(
            "propiedades",
            {"org_id": f"eq.{org_id}", "select": "fotos"},
            timeout=30,
        )
        for fila in filas_pendientes:
            fotos = fila.get("fotos") or []
            if isinstance(fotos, list) and any(_foto_migrable(f) for f in fotos):
                pendientes += 1
    except Exception:
        pass
    return {"pendientes": pendientes, "en_proceso": org_id in _fotos_en_proceso}


@router.post("/easybroker/migrar-fotos")
async def easybroker_migrar_fotos(request: Request):
    """Migrate one keyset-paginated batch of external property photos."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        raise HTTPException(status_code=403, detail="Tu cuenta no está configurada. Contacta a soporte.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    cursor = (body or {}).get("cursor")

    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    CHUNK = 10
    params = {
        "org_id": f"eq.{org_id}",
        "select": "id,fotos",
        "order": "id.asc",
        "limit": str(CHUNK),
    }
    if cursor:
        params["id"] = f"gt.{cursor}"
    try:
        filas = await get_rows("propiedades", params, timeout=30)
    except Exception:
        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")

    propiedades_ok = 0
    fotos_subidas = 0
    errores = 0
    ultimo_id = cursor

    async def _subir_una(client, url):
        try:
            rd = await client.get(url, timeout=30.0, follow_redirects=True)
            if rd.status_code != 200 or not rd.content:
                return None
            mime = (rd.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
            raw = rd.content
        except Exception:
            return None
        ext = _EXT_POR_MIME.get(mime, "jpg")
        nombre = f"{_uuid.uuid4().hex}.{ext}"
        try:
            ru = await client.post(
                f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}/{nombre}",
                headers={**sb_headers, "Content-Type": mime},
                content=raw, timeout=60.0,
            )
        except Exception:
            return None
        if ru.status_code not in (200, 201):
            return None
        return f"{SUPABASE_URL}/storage/v1/object/public/{_FOTOS_BUCKET}/{nombre}"

    async def _resolver(client, f):
        if _foto_migrable(f):
            return (f, await _subir_una(client, f))
        return (f, None)

    async with httpx.AsyncClient(timeout=60) as client:
        for fila in filas:
            pid = fila.get("id")
            ultimo_id = pid
            fotos = fila.get("fotos") or []
            if not isinstance(fotos, list) or not any(_foto_migrable(f) for f in fotos):
                continue

            nuevas = []
            subidas_prop = 0
            i = 0
            while i < len(fotos):
                lote = fotos[i:i+4]
                resultados = await asyncio.gather(*[_resolver(client, f) for f in lote])
                for original, nueva in resultados:
                    if _foto_migrable(original) and nueva:
                        nuevas.append(nueva)
                        subidas_prop += 1
                    else:
                        nuevas.append(original)
                i += 4

            if subidas_prop == 0:
                continue
            try:
                await patch_rows(
                    "propiedades",
                    {"id": f"eq.{pid}"},
                    {"fotos": nuevas},
                    timeout=60,
                    accepted_statuses=(200, 204),
                )
                propiedades_ok += 1
                fotos_subidas += subidas_prop
            except Exception:
                errores += 1

    hay_mas = len(filas) == CHUNK
    return {
        "propiedades_actualizadas": propiedades_ok,
        "fotos_subidas": fotos_subidas,
        "errores": errores,
        "cursor": ultimo_id,
        "hay_mas": hay_mas,
    }
