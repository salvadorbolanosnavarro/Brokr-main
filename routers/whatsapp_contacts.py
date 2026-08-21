"""WhatsApp number, agenda, contact and conversation persistence helpers."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from routers.whatsapp_crm_bridge import crear_contacto_crm
from routers.whatsapp_data import sb_get, sb_patch, sb_post
from routers.whatsapp_identity import solo_digitos


log = logging.getLogger("broquer.whatsapp2")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_numero(phone_number_id: str) -> dict | None:
    rows = await sb_get(
        "wa2_numeros",
        {"phone_number_id": f"eq.{phone_number_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def agenda_upsert(
    user_id: str,
    numero_id: str,
    telefono: str,
    nombre: str | None = None,
    conocido: bool | None = None,
) -> None:
    try:
        rows = await sb_get(
            "wa2_agenda",
            {"numero_id": f"eq.{numero_id}", "telefono": f"eq.{telefono}", "select": "*", "limit": "1"},
        )
        if rows:
            cambios = {"updated_at": _now()}
            if nombre:
                cambios["nombre"] = nombre
            if conocido is not None:
                cambios["conocido"] = conocido
            await sb_patch("wa2_agenda", {"id": f"eq.{rows[0]['id']}"}, cambios)
        else:
            await sb_post(
                "wa2_agenda",
                {
                    "user_id": user_id,
                    "numero_id": numero_id,
                    "telefono": telefono,
                    "nombre": nombre,
                    "conocido": bool(conocido),
                    "created_at": _now(),
                    "updated_at": _now(),
                },
            )
    except Exception as exc:
        log.warning("wa2_agenda no se pudo actualizar (%s): %s", telefono, exc)


async def get_o_crea_contacto(
    user_id: str,
    numero_id: str,
    wa_id: str,
    nombre: str | None,
    crear_crm: bool = True,
) -> dict:
    rows = await sb_get(
        "wa2_contactos",
        {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}", "select": "*", "limit": "1"},
    )
    if rows:
        return rows[0]
    agenda = await sb_get(
        "wa2_agenda",
        {"numero_id": f"eq.{numero_id}", "telefono": f"eq.{solo_digitos(wa_id)}", "select": "*", "limit": "1"},
    )
    nombre_agenda = (agenda[0].get("nombre") or "").strip() if agenda else ""
    conocido = bool(agenda and agenda[0].get("conocido"))
    display = nombre_agenda or (nombre or "").strip() or None
    contacto_crm_id = await crear_contacto_crm(user_id, wa_id, display) if crear_crm else None
    created = await sb_post(
        "wa2_contactos",
        {
            "user_id": user_id,
            "numero_id": numero_id,
            "wa_id": wa_id,
            "nombre": display,
            "nombre_agenda": nombre_agenda or None,
            "nombre_wa": nombre or None,
            "conocido": conocido,
            "contacto_crm_id": contacto_crm_id,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )
    if created:
        return created[0]
    rows = await sb_get(
        "wa2_contactos",
        {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else {}


async def get_o_crea_conversacion(
    user_id: str,
    numero_id: str,
    contacto_id: str,
    ia_default: bool = True,
) -> dict:
    rows = await sb_get(
        "wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"}
    )
    if rows:
        return rows[0]
    fila = {
        "user_id": user_id,
        "numero_id": numero_id,
        "contacto_id": contacto_id,
        "ai_enabled": ia_default,
        "ia_modo": "auto" if ia_default else "off",
        "ia_sesion_nueva": bool(ia_default),
        "created_at": _now(),
        "last_message_at": _now(),
    }
    created = await sb_post("wa2_conversaciones", fila)
    if not created:
        fila.pop("ia_modo", None)
        fila.pop("ia_sesion_nueva", None)
        created = await sb_post("wa2_conversaciones", fila)
    if created:
        return created[0]
    rows = await sb_get(
        "wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"}
    )
    return rows[0] if rows else {}
