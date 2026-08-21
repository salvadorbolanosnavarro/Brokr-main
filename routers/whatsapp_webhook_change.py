"""Process one Meta WhatsApp webhook change value."""
from __future__ import annotations

import logging

from routers.whatsapp_coexistence import procesar_coexistencia
from routers.whatsapp_contacts import get_numero
from routers.whatsapp_delivery_status import procesar_statuses
from routers.whatsapp_incoming import persistir_mensaje_entrante


log = logging.getLogger("broquer.whatsapp2")


async def procesar_change_value(val: dict) -> list[dict]:
    phone_number_id = (val.get("metadata") or {}).get("phone_number_id")
    if not phone_number_id:
        return []
    numero = await get_numero(phone_number_id)
    if not numero:
        log.warning("Número no registrado en wa2_numeros: %s — ignorado", phone_number_id)
        return []

    contactos_meta = {
        contacto["wa_id"]: contacto.get("profile", {}).get("name")
        for contacto in val.get("contacts", [])
    }

    await procesar_coexistencia(val, numero)

    trabajo = []
    for msg in val.get("messages", []):
        item = await persistir_mensaje_entrante(msg, numero, contactos_meta)
        if item:
            trabajo.append(item)

    await procesar_statuses(val, numero)
    return trabajo
