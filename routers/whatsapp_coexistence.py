"""WhatsApp Business app coexistence synchronization."""
from __future__ import annotations

from datetime import datetime, timezone

from routers.whatsapp_contacts import (
    agenda_upsert,
    get_o_crea_contacto,
    get_o_crea_conversacion,
)
from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_handoff import entrenamiento_de, pausar_por_respuesta_manual
from routers.whatsapp_identity import es_asesor, solo_digitos
from routers.whatsapp_messages import guardar_mensaje


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def procesar_coexistencia(val: dict, numero: dict) -> None:
    """Mirror advisor echoes, phone contacts and prior-history familiarity."""
    entren_eco = None
    for eco in (val.get("message_echoes") or []):
        wa_dest = solo_digitos(eco.get("to") or "")
        if not wa_dest:
            continue
        ya = await sb_get(
            "wa2_mensajes",
            {"wa_message_id": f"eq.{eco.get('id')}", "select": "id", "limit": "1"},
        )
        if ya:
            continue
        if eco.get("type") == "text":
            cuerpo = (eco.get("text") or {}).get("body", "")
        else:
            cuerpo = f"[{eco.get('type') or 'mensaje'} enviado por el asesor desde su celular]"

        if es_asesor(numero, wa_dest):
            contacto_self = await get_o_crea_contacto(
                numero["user_id"],
                numero["id"],
                wa_dest,
                "Tú · Broq",
                crear_crm=False,
            )
            if not contacto_self:
                continue
            conv_self = await get_o_crea_conversacion(
                numero["user_id"],
                numero["id"],
                contacto_self["id"],
                ia_default=False,
            )
            await guardar_mensaje(
                numero["user_id"],
                contacto_self["id"],
                conv_self["id"],
                eco.get("id"),
                "out",
                "agente",
                cuerpo,
            )
            continue

        contacto_eco = await get_o_crea_contacto(
            numero["user_id"],
            numero["id"],
            wa_dest,
            None,
        )
        if not contacto_eco:
            continue
        conv_eco = await get_o_crea_conversacion(
            numero["user_id"],
            numero["id"],
            contacto_eco["id"],
            ia_default=False,
        )
        await guardar_mensaje(
            numero["user_id"],
            contacto_eco["id"],
            conv_eco["id"],
            eco.get("id"),
            "out",
            "agente",
            cuerpo,
        )
        if entren_eco is None:
            entren_eco = await entrenamiento_de(numero["user_id"], numero["id"])
        await pausar_por_respuesta_manual(conv_eco, numero, entren_eco)
        if not contacto_eco.get("conocido"):
            await sb_patch(
                "wa2_contactos",
                {"id": f"eq.{contacto_eco['id']}"},
                {"conocido": True, "updated_at": _now()},
            )
            await agenda_upsert(
                numero["user_id"],
                numero["id"],
                wa_dest,
                conocido=True,
            )

    for sync in (val.get("state_sync") or []):
        if sync.get("type") != "contact":
            continue
        contacto_sync = sync.get("contact") or {}
        telefono = solo_digitos(contacto_sync.get("phone_number") or "")
        nombre = (
            contacto_sync.get("full_name")
            or contacto_sync.get("first_name")
            or ""
        ).strip()
        if not telefono or (sync.get("action") or "add") == "remove":
            continue
        await agenda_upsert(
            numero["user_id"],
            numero["id"],
            telefono,
            nombre=nombre or None,
        )
        filas = await sb_get(
            "wa2_contactos",
            {
                "numero_id": f"eq.{numero['id']}",
                "wa_id": f"eq.{telefono}",
                "select": "*",
                "limit": "1",
            },
        )
        if filas and nombre:
            contacto = filas[0]
            cambios = {"nombre_agenda": nombre, "updated_at": _now()}
            if not (contacto.get("nombre_chat") or "").strip():
                cambios["nombre"] = nombre
            await sb_patch("wa2_contactos", {"id": f"eq.{contacto['id']}"}, cambios)

    for bloque in (val.get("history") or []):
        for hilo in (bloque.get("threads") or []):
            telefono = solo_digitos(str(hilo.get("id") or ""))
            if telefono:
                await agenda_upsert(
                    numero["user_id"],
                    numero["id"],
                    telefono,
                    conocido=True,
                )
