"""Shared state and predicates for EasyBroker property-photo migration."""
from __future__ import annotations

from core.config import settings


FOTOS_BUCKET = "fotos-propiedades"

# org_id values with an active background migration worker.
fotos_en_proceso: set[str] = set()


def foto_ya_es_de_broquer(url) -> bool:
    """Return True when the URL already belongs to Broquer's Supabase Storage."""
    return isinstance(url, str) and bool(settings.supabase_url) and settings.supabase_url in url


def foto_migrable(url) -> bool:
    """Return True for an external HTTP image URL worth migrating to Broquer."""
    return (
        isinstance(url, str)
        and url.startswith("http")
        and not foto_ya_es_de_broquer(url)
    )


async def importar_foto_externa(url: str, *, comprimir=None) -> str | None:
    """Descarga una foto externa (EasyBroker u otra URL) y la guarda en Broquer.

    Única puerta para importar fotos de terceros:
      * descarga con ``core.http`` (bloquea direcciones internas y redirecciones
        peligrosas, y limita el tamaño);
      * valida el contenido real con ``core.file_validation`` (perfil
        ``foto_importada``): una "foto" que en realidad es HTML no se guarda;
      * guarda con nombre UUID y el Content-Type del tipo real, nunca el que
        dijo el servidor remoto.
    ``comprimir(raw) -> (bytes|None, mime, ext)`` es opcional.
    Regresa la URL pública nueva o ``None`` si la foto no se pudo importar.
    """
    import asyncio

    from core.file_validation import PERFILES, validar_archivo
    from core.http import fetch_public_bytes
    from core.storage import upload_object

    try:
        raw = await fetch_public_bytes(url, timeout=30, max_bytes=PERFILES["foto_importada"].max_bytes)
        # Sin nombre: en una URL remota solo cuenta el contenido.
        val = validar_archivo(raw, None, "foto_importada")
    except Exception:  # incluye ArchivoRechazado y URLs inseguras
        return None
    if comprimir is not None:
        try:
            comp, _mime, ext = await asyncio.to_thread(comprimir, raw)
            if comp:
                val = validar_archivo(comp, None, "foto_importada")
                raw = comp
        except Exception:
            pass
    try:
        return await upload_object(FOTOS_BUCKET, val.nombre_interno, raw, content_type=val.mime, timeout=60)
    except Exception:
        return None
