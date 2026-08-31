"""Shared persistence for WhatsApp messages and conversation activity."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from routers.whatsapp_data import sb_get, sb_patch, sb_post


log = logging.getLogger("broquer.whatsapp2")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def guardar_mensaje(
    user_id: str,
    contacto_id: str,
    conversacion_id: str,
    wamid: str | None,
    direction: str,
    sender: str,
    body: str,
    media_url: str | None = None,
    media_path: str | None = None,
) -> None:
    fila = {
        "user_id": user_id,
        "contacto_id": contacto_id,
        "conversacion_id": conversacion_id,
        "direction": direction,
        "sender": sender,
        "body": body,
        "media_url": media_url,
        "media_path": media_path,
        "created_at": _now(),
    }
    if wamid:
        fila["wa_message_id"] = wamid
    guardado = await sb_post("wa2_mensajes", fila)
    if not guardado and wamid:
        ya = await sb_get(
            "wa2_mensajes",
            {"wa_message_id": f"eq.{wamid}", "select": "id", "limit": "1"},
        )
        if not ya:
            log.error("wa2_mensajes NO guardado: conv=%s sender=%s", conversacion_id, sender)
    cambios_conv = {"last_message_at": _now()}
    if direction == "in":
        cambios_conv["last_inbound_at"] = _now()
        if wamid:
            cambios_conv["last_inbound_wamid"] = wamid
    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios_conv)
