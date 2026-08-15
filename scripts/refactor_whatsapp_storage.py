#!/usr/bin/env python3
"""Move WhatsApp 2 Supabase Storage operations to core.storage."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

OLD_IMPORT = '''from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers
'''
NEW_IMPORT = '''from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.storage import delete_objects, upload_object
'''

OLD_SUPABASE_ALIASES = '''SUPABASE_URL         = settings.supabase_url
SUPABASE_ANON_KEY    = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
'''

OLD_HEADERS = '''def _sb_headers() -> dict:
    # Temporary adapter for non-table Supabase calls (for example Storage).
    # Credential policy itself lives in core.database.
    return service_headers()


'''

OLD_UPLOAD = '''async def _guardar_archivo(user_id: str, conversacion_id: str, contenido: bytes,
                           mime: str, sufijo: str) -> tuple[str | None, str | None]:
    """Sube a Supabase el archivo que mandó el prospecto y devuelve
    (url_publica, ruta_interna).

    Hace falta guardarlo porque la liga que da Meta caduca en minutos y además
    exige el token del número: si solo se guardara esa liga, mañana estaría
    muerta y el agente no podría volver a ver la foto que le mandaron.
    La ruta interna se conserva aparte para poder BORRAR el archivo después."""
    if not contenido or not SUPABASE_URL:
        return None, None
    ext = (mime.split("/")[-1] or "bin").split(";")[0][:8] or "bin"
    ruta = f"{user_id}/{conversacion_id}/{int(datetime.now(timezone.utc).timestamp()*1000)}-{sufijo}.{ext}"
    try:
        h = {k: v for k, v in _sb_headers().items() if k != "Content-Type"}
        h["Content-Type"] = mime or "application/octet-stream"
        h["x-upsert"] = "true"
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{WA_MEDIA_BUCKET}/{ruta}",
                             headers=h, content=contenido)
        if r.status_code >= 300:
            log.warning("No se pudo guardar el archivo de WhatsApp: %s %s", r.status_code, r.text[:200])
            return None, None
        return f"{SUPABASE_URL}/storage/v1/object/public/{WA_MEDIA_BUCKET}/{ruta}", ruta
    except Exception as e:
        log.warning("Error guardando archivo de WhatsApp: %s", e)
        return None, None
'''
NEW_UPLOAD = '''async def _guardar_archivo(user_id: str, conversacion_id: str, contenido: bytes,
                           mime: str, sufijo: str) -> tuple[str | None, str | None]:
    """Persist media through the canonical Storage layer and keep its path."""
    if not contenido:
        return None, None
    ext = (mime.split("/")[-1] or "bin").split(";")[0][:8] or "bin"
    ruta = f"{user_id}/{conversacion_id}/{int(datetime.now(timezone.utc).timestamp()*1000)}-{sufijo}.{ext}"
    try:
        url = await upload_object(
            WA_MEDIA_BUCKET,
            ruta,
            contenido,
            content_type=mime or "application/octet-stream",
            timeout=40,
        )
        return url, ruta
    except Exception as e:
        log.warning("Error guardando archivo de WhatsApp: %s", e)
        return None, None
'''

OLD_DELETE = '''async def _borrar_archivos(rutas: list) -> None:
    """Borra del almacenamiento los archivos de los mensajes que se eliminan.
    Si esto no se hiciera, la foto seguiría viva en una liga pública aunque el
    mensaje ya no apareciera en ningún lado — que es justo lo contrario de lo
    que promete una supresión."""
    rutas = [r for r in (rutas or []) if r]
    if not rutas:
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.request("DELETE", f"{SUPABASE_URL}/storage/v1/object/{WA_MEDIA_BUCKET}",
                            headers=_sb_headers(), json={"prefixes": rutas})
    except Exception as e:
        log.warning("No se pudieron borrar %s archivo(s) del almacenamiento: %s", len(rutas), e)
'''
NEW_DELETE = '''async def _borrar_archivos(rutas: list) -> None:
    """Delete persisted message media while keeping message deletion resilient."""
    rutas = [r for r in (rutas or []) if r]
    if not rutas:
        return
    try:
        await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)
    except Exception as e:
        log.warning("No se pudieron borrar %s archivo(s) del almacenamiento: %s", len(rutas), e)
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"WhatsApp Storage {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.storage import delete_objects, upload_object" in text:
        raise RuntimeError("WhatsApp Storage refactor already appears applied")
    text = _replace_once(text, OLD_IMPORT, NEW_IMPORT, "imports")
    text = _replace_once(text, OLD_SUPABASE_ALIASES, "", "Supabase aliases")
    text = _replace_once(text, OLD_HEADERS, "", "header adapter")
    text = _replace_once(text, OLD_UPLOAD, NEW_UPLOAD, "media upload")
    text = _replace_once(text, OLD_DELETE, NEW_DELETE, "batch media delete")
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "whatsapp.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
