#!/usr/bin/env python3
"""One-shot exact transform for Firmas DB/Storage infrastructure."""
from __future__ import annotations

from pathlib import Path


IMPORT_OLD = '''from core.auth import require_user_id
from core.config import settings
from core.subscriptions import require_paid_feature_access
'''

IMPORT_NEW = '''from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.storage import create_signed_object_url, delete_object, download_object, upload_object
from core.subscriptions import require_paid_feature_access
'''

DB_OLD = '''def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code != 200:
            log.warning("GET %s -> %s %s", tabla, r.status_code, r.text[:180])
            return []
        return r.json()


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(prefer), json=payload)
        if r.status_code not in (200, 201, 204):
            log.warning("POST %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tabla}",
                          headers=_headers("return=representation"),
                          params=params, json=payload)
        if r.status_code not in (200, 204):
            log.warning("PATCH %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.")
        try:
            return r.json()
        except Exception:
            return []


async def _sb_delete(tabla: str, params: dict) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.delete(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=_headers(), params=params)
        if r.status_code not in (200, 204):
            log.warning("DELETE %s -> %s %s", tabla, r.status_code, r.text[:180])
            raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.")
'''

DB_NEW = '''def _db_error(exc: Exception) -> tuple[str, str]:
    """Return status/text for logging without leaking Core exceptions to callers."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return str(exc.response.status_code), (exc.response.text or "")[:180]
    return "error", str(exc)[:180]


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except Exception as exc:
        status, text = _db_error(exc)
        log.warning("GET %s -> %s %s", tabla, status, text)
        return []


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    try:
        return await post_rows(tabla, payload, prefer=prefer, timeout=20)
    except Exception as exc:
        status, text = _db_error(exc)
        log.warning("POST %s -> %s %s", tabla, status, text)
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    try:
        return await patch_rows(
            tabla,
            params,
            payload,
            prefer="return=representation",
            timeout=20,
        )
    except Exception as exc:
        status, text = _db_error(exc)
        log.warning("PATCH %s -> %s %s", tabla, status, text)
        raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.") from exc


async def _sb_delete(tabla: str, params: dict) -> None:
    try:
        await delete_rows(tabla, params, timeout=20)
    except Exception as exc:
        status, text = _db_error(exc)
        log.warning("DELETE %s -> %s %s", tabla, status, text)
        raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.") from exc
'''

STORAGE_OLD = '''async def _subir_bytes(ruta: str, contenido: bytes, mime: str) -> None:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": mime, "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")


async def _bajar_bytes(ruta: str) -> bytes:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.get(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                        headers={"apikey": SUPABASE_SERVICE_KEY,
                                 "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
        if r.status_code != 200:
            log.warning("download %s -> %s", ruta, r.status_code)
            raise HTTPException(500, "No se pudo leer el archivo guardado.")
        return r.content


async def _liga_firmada(ruta: str, segundos: int) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": segundos})
        if r.status_code != 200:
            log.warning("sign %s -> %s %s", ruta, r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo abrir el archivo.")
        return f"{SUPABASE_URL}/storage/v1" + (r.json().get("signedURL") or "")


async def _borrar_ruta(ruta: str) -> None:
    if not ruta:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.delete(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                           headers={"apikey": SUPABASE_SERVICE_KEY,
                                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
    except Exception as e:
        log.warning("no se pudo borrar %s: %s", ruta, e)
'''

STORAGE_NEW = '''async def _subir_bytes(ruta: str, contenido: bytes, mime: str) -> None:
    try:
        await upload_object(BUCKET, ruta, contenido, content_type=mime, timeout=90)
    except Exception as exc:
        log.warning("upload %s -> %s", ruta, exc)
        raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.") from exc


async def _bajar_bytes(ruta: str) -> bytes:
    try:
        return await download_object(BUCKET, ruta, timeout=90)
    except Exception as exc:
        log.warning("download %s -> %s", ruta, exc)
        raise HTTPException(500, "No se pudo leer el archivo guardado.") from exc


async def _liga_firmada(ruta: str, segundos: int) -> str:
    try:
        return await create_signed_object_url(
            BUCKET,
            ruta,
            expires_in=segundos,
            timeout=15,
        )
    except Exception as exc:
        log.warning("sign %s -> %s", ruta, exc)
        raise HTTPException(500, "No se pudo abrir el archivo.") from exc


async def _borrar_ruta(ruta: str) -> None:
    if not ruta:
        return
    try:
        await delete_object(BUCKET, ruta, timeout=20, ignore_missing=True)
    except Exception as exc:
        # Historical behavior is best-effort cleanup: deletion must never
        # invalidate an otherwise completed signature operation.
        log.warning("no se pudo borrar %s: %s", ruta, exc)
'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} block, found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    consent = source[source.index("CONSENTIMIENTO = ("):source.index("\n\n\n# ═", source.index("CONSENTIMIENTO = ("))]
    sha_func = '''def _sha256(b: bytes) -> str:\n    return hashlib.sha256(b).hexdigest()\n'''
    if sha_func not in source:
        raise RuntimeError("Firmas SHA-256 invariant function was not found")

    updated = _replace_once(source, IMPORT_OLD, IMPORT_NEW, "Core import")
    updated = _replace_once(updated, DB_OLD, DB_NEW, "database infrastructure")
    updated = _replace_once(updated, STORAGE_OLD, STORAGE_NEW, "storage infrastructure")

    if "/rest/v1/" in updated:
        raise RuntimeError("Direct Supabase REST remains in Firmas")
    if "/storage/v1/object/" in updated:
        raise RuntimeError("Direct Supabase Storage remains in Firmas")
    if consent not in updated:
        raise RuntimeError("Consent text changed during infrastructure transform")
    if sha_func not in updated:
        raise RuntimeError("SHA-256 invariant changed during infrastructure transform")
    compile(updated, "routers/firmas.py", "exec")
    return updated


def main() -> None:
    path = Path("routers/firmas.py")
    source = path.read_text(encoding="utf-8")
    updated = transform(source)
    if updated == source:
        raise RuntimeError("Transform made no change")
    path.write_text(updated, encoding="utf-8")
    print("Firmas database and Storage now delegate to Core")


if __name__ == "__main__":
    main()
