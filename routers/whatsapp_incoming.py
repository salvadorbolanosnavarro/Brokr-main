"""Persist one inbound Meta WhatsApp message and build its processing work item."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from routers.whatsapp_contacts import get_o_crea_contacto, get_o_crea_conversacion
from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_identity import es_asesor
from routers.whatsapp_media_storage import guardar_archivo
from routers.whatsapp_messages import guardar_mensaje
from routers.whatsapp_webhook_messages import materializar_mensaje


log = logging.getLogger("broquer.whatsapp2")
OPT_OUT_PALABRAS = {
    "baja",
    "stop",
    "alto",
    "cancelar",
    "no molestar",
    "darme de baja",
    "no me escribas",
    "unsubscribe",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def persistir_mensaje_entrante(
    msg: dict,
    numero: dict,
    contactos_meta: dict,
) -> dict | None:
    wa_id = msg.get("from")
    if not wa_id:
        return None

    try:
        msg_ts = int(msg.get("timestamp") or 0)
        creado_en = numero.get("created_at")
        if msg_ts and creado_en:
            creado_dt = datetime.fromisoformat(creado_en.replace("Z", "+00:00"))
            if datetime.fromtimestamp(msg_ts, timezone.utc) < creado_dt:
                log.warning(
                    "Mensaje anterior a la conexión del número %s — ignorado (%s)",
                    numero.get("phone_number_id"),
                    msg.get("id"),
                )
                return None
    except Exception:
        pass

    existe = await sb_get(
        "wa2_mensajes",
        {"wa_message_id": f"eq.{msg.get('id')}", "select": "id", "limit": "1"},
    )
    if existe:
        return None

    tipo_msg, texto, media_bytes, media_mime, media_sufijo = await materializar_mensaje(
        msg,
        numero,
    )

    asesor = es_asesor(numero, wa_id)
    if asesor:
        contacto = await get_o_crea_contacto(
            numero["user_id"],
            numero["id"],
            wa_id,
            "Tú · Broq",
            crear_crm=False,
        )
        conv = await get_o_crea_conversacion(
            numero["user_id"],
            numero["id"],
            contacto["id"],
            ia_default=False,
        )
    else:
        contacto = await get_o_crea_contacto(
            numero["user_id"],
            numero["id"],
            wa_id,
            contactos_meta.get(wa_id),
        )
        conv = await get_o_crea_conversacion(
            numero["user_id"],
            numero["id"],
            contacto["id"],
            ia_default=not contacto.get("conocido"),
        )

    media_url, media_path = None, None
    if media_bytes:
        media_url, media_path = await guardar_archivo(
            numero["user_id"],
            conv["id"],
            media_bytes,
            media_mime,
            media_sufijo,
        )

    await guardar_mensaje(
        numero["user_id"],
        contacto["id"],
        conv["id"],
        msg.get("id"),
        "in",
        "agente" if asesor else "lead",
        texto,
        media_url,
        media_path,
    )
    if not asesor:
        await sb_patch(
            "wa2_conversaciones",
            {"id": f"eq.{conv['id']}"},
            {"unread_count": (conv.get("unread_count") or 0) + 1},
        )

    if (
        not asesor
        and tipo_msg == "text"
        and texto.strip().lower().rstrip(".!") in OPT_OUT_PALABRAS
    ):
        try:
            await sb_patch(
                "wa2_contactos",
                {"id": f"eq.{contacto['id']}"},
                {"opt_out": True, "updated_at": _now()},
            )
        except Exception:
            pass

    return {
        "numero": numero,
        "contacto_id": contacto["id"],
        "conversacion_id": conv["id"],
        "wa_id": wa_id,
        "texto": texto,
        "wa_message_id": msg.get("id"),
        "es_asesor": asesor,
        "prev_inbound_at": conv.get("last_inbound_at"),
    }
