"""Handle failed WhatsApp delivery receipts from Meta webhooks."""
from __future__ import annotations

import logging

from routers.whatsapp_cloud_api import revisar_token
from routers.whatsapp_data import sb_patch

try:
    from push import enviar_push
except Exception:  # pragma: no cover
    async def enviar_push(*args, **kwargs):
        return False


log = logging.getLogger("broquer.whatsapp2")


async def procesar_statuses(val: dict, numero: dict) -> None:
    for status in val.get("statuses", []):
        estado = status.get("status")
        if estado != "failed":
            continue
        errores = status.get("errors") or [{}]
        error = errores[0] if errores else {}
        log.error(
            "Mensaje NO entregado (%s): %s %s",
            numero.get("phone_number_id"),
            error.get("code"),
            error.get("title"),
        )
        await revisar_token(
            numero,
            {"code": error.get("code"), "message": error.get("title") or ""},
        )
        try:
            await sb_patch(
                "wa2_mensajes",
                {"wa_message_id": f"eq.{status.get('id')}"},
                {"entrega_error": (error.get("title") or "No se pudo entregar")[:200]},
            )
        except Exception:
            pass
        await enviar_push(
            numero.get("user_id"),
            "Un mensaje no se pudo entregar",
            error.get("title") or "WhatsApp rechazó el envío. Revisa la conversación.",
            datos={"tipo": "whatsapp"},
        )
