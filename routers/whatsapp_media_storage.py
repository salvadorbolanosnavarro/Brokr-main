"""Canonical Storage-backed persistence for WhatsApp media."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from core.config import settings
from core.storage import delete_objects, upload_object


log = logging.getLogger("broquer.whatsapp2")
WA_MEDIA_BUCKET = settings.wa2_media_bucket


async def guardar_archivo(user_id: str, conversacion_id: str, contenido: bytes,
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


async def borrar_archivos(rutas: list) -> None:
    """Delete persisted message media while keeping message deletion resilient."""
    rutas = [r for r in (rutas or []) if r]
    if not rutas:
        return
    try:
        await delete_objects(WA_MEDIA_BUCKET, rutas, timeout=20)
    except Exception as e:
        log.warning("No se pudieron borrar %s archivo(s) del almacenamiento: %s", len(rutas), e)
