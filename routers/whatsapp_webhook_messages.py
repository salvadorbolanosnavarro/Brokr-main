"""Materialize one Meta webhook message into Broquer's internal message fields."""
from __future__ import annotations

import re

from routers.whatsapp_cloud_api import descargar_media
from routers.whatsapp_media_ai import describir_imagen, transcribir_audio


async def materializar_mensaje(msg: dict, numero: dict) -> tuple[str | None, str, bytes | None, str, str]:
    """Return (type, text, media bytes, mime, suffix) with legacy fallbacks."""
    tipo_msg = msg.get("type")
    texto = ""
    media_bytes: bytes | None = None
    media_mime = ""
    media_sufijo = "archivo"

    if tipo_msg == "text":
        texto = (msg.get("text") or {}).get("body", "")
    elif tipo_msg in ("audio", "voice"):
        media_id = (msg.get(tipo_msg) or {}).get("id")
        media_bytes, media_mime = await descargar_media(numero, media_id)
        media_sufijo = "nota-de-voz"
        dicho = (
            await transcribir_audio(media_bytes, media_mime, numero.get("user_id") or "")
            if media_bytes
            else ""
        )
        texto = (
            f"[nota de voz] {dicho}"
            if dicho
            else "[nota de voz que no se pudo transcribir]"
        )
    elif tipo_msg == "image":
        media_id = (msg.get("image") or {}).get("id")
        pie = (msg.get("image") or {}).get("caption") or ""
        media_bytes, media_mime = await descargar_media(numero, media_id)
        media_sufijo = "foto"
        visto = (
            await describir_imagen(media_bytes, media_mime, numero.get("user_id") or "")
            if media_bytes
            else ""
        )
        texto = "[foto] " + " ".join(value for value in [pie, visto] if value).strip()
        if not visto and not pie:
            texto = "[foto que no se pudo leer]"
    elif tipo_msg == "location":
        loc = msg.get("location") or {}
        partes_loc = [
            loc.get("name"),
            loc.get("address"),
            f"{loc.get('latitude')},{loc.get('longitude')}",
        ]
        texto = "[ubicación] " + " · ".join(str(value) for value in partes_loc if value)
    elif tipo_msg == "document":
        doc = msg.get("document") or {}
        media_bytes, media_mime = await descargar_media(numero, doc.get("id"))
        media_sufijo = re.sub(
            r"[^A-Za-z0-9._-]",
            "_",
            doc.get("filename") or "documento",
        )[:60]
        texto = f"[documento] {doc.get('filename') or ''} {doc.get('caption') or ''}".strip()
    elif tipo_msg == "video":
        video = msg.get("video") or {}
        media_bytes, media_mime = await descargar_media(numero, video.get("id"))
        media_sufijo = "video"
        texto = f"[video] {video.get('caption') or ''}".strip()
    elif tipo_msg == "contacts":
        texto = "[el prospecto compartió una tarjeta de contacto]"
    elif tipo_msg in ("button", "interactive"):
        interactive = msg.get("interactive") or {}
        texto = (
            (msg.get("button") or {}).get("text")
            or (interactive.get("button_reply") or {}).get("title")
            or (interactive.get("list_reply") or {}).get("title")
            or "[respuesta a un botón]"
        )
    else:
        texto = f"[mensaje de tipo {tipo_msg or 'desconocido'}]"

    return tipo_msg, texto, media_bytes, media_mime, media_sufijo
