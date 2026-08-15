#!/usr/bin/env python3
"""Migrate Finanzas private Storage operations to core.storage."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "finanzas.py"

OLD_DB_IMPORT = "from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers\n"
NEW_DB_IMPORT = '''from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.storage import create_signed_object_url, delete_object, upload_object
'''

OLD_CONFIG = '''SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
'''
NEW_CONFIG = '''ANTHROPIC_API_KEY = settings.anthropic_api_key
'''

OLD_HEADERS = '''def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    # Temporary compatibility adapter for the Storage code below. Database
    # operations themselves use core.database directly.
    return service_headers(prefer=prefer)


'''

OLD_DELETE = '''    if ruta:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                await c.delete(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                               headers=_headers())
        except Exception:
            pass  # el registro se borra igual; un huérfano en storage no rompe nada
'''
NEW_DELETE = '''    if ruta:
        try:
            await delete_object(BUCKET, ruta, timeout=20)
        except Exception:
            pass  # el registro se borra igual; un huérfano en storage no rompe nada
'''

OLD_UPLOAD = '''    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                         headers={"apikey": SUPABASE_SERVICE_KEY,
                                  "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                  "Content-Type": mime, "x-upsert": "true"},
                         content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload comprobante -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")
'''
NEW_UPLOAD = '''    try:
        await upload_object(
            BUCKET,
            ruta,
            contenido,
            content_type=mime,
            timeout=60,
        )
    except Exception as exc:
        log.warning("upload comprobante falló: %s", exc)
        raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.") from exc
'''

OLD_SIGNED = '''    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": 300})
        if r.status_code != 200:
            raise HTTPException(500, "No se pudo generar la liga.")
        firmada = r.json().get("signedURL", "")
    return {"url": f"{SUPABASE_URL}/storage/v1{firmada}"}
'''
NEW_SIGNED = '''    try:
        firmada = await create_signed_object_url(
            BUCKET,
            ruta,
            expires_in=300,
            timeout=15,
        )
    except Exception as exc:
        raise HTTPException(500, "No se pudo generar la liga.") from exc
    return {"url": firmada}
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Finanzas {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.storage import create_signed_object_url" in text:
        raise RuntimeError("Finanzas Storage refactor already appears applied")
    text = _replace_once(text, OLD_DB_IMPORT, NEW_DB_IMPORT, "imports")
    text = _replace_once(text, OLD_CONFIG, NEW_CONFIG, "config aliases")
    text = _replace_once(text, OLD_HEADERS, "", "temporary headers")
    text = _replace_once(text, OLD_DELETE, NEW_DELETE, "delete object")
    text = _replace_once(text, OLD_UPLOAD, NEW_UPLOAD, "upload object")
    text = _replace_once(text, OLD_SIGNED, NEW_SIGNED, "signed URL")
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    compile(updated, "routers/finanzas.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
