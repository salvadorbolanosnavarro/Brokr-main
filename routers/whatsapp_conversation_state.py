"""WhatsApp contact/conversation creation helpers.

Kept dependency-injected so root compatibility wrappers preserve runtime monkeypatches.
"""
from __future__ import annotations


async def _get_o_crea_contacto_core(user_id: str, numero_id: str, wa_id: str, nombre: str | None,
                                    crear_crm: bool = True, *, sb_get, _solo_digitos,
                                    _crear_contacto_crm, sb_post, _now) -> dict:
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    # Prioridad de nombre del lead: 1) cómo se presentó él mismo en el chat (lo
    # llena la IA cuando lo diga), 2) cómo lo tiene el asesor en la agenda de su
    # celular, 3) el nombre que el lead se puso en WhatsApp SOLO como último
    # recurso, cuando no existen los otros dos.
    agenda = await sb_get("wa2_agenda", {"numero_id": f"eq.{numero_id}",
                                         "telefono": f"eq.{_solo_digitos(wa_id)}",
                                         "select": "*", "limit": "1"})
    nombre_agenda = (agenda[0].get("nombre") or "").strip() if agenda else ""
    conocido = bool(agenda and agenda[0].get("conocido"))
    display = nombre_agenda or (nombre or "").strip() or None
    contacto_crm_id = await _crear_contacto_crm(user_id, wa_id, display) if crear_crm else None
    created = await sb_post("wa2_contactos", {
        "user_id": user_id, "numero_id": numero_id, "wa_id": wa_id,
        "nombre": display, "nombre_agenda": nombre_agenda or None,
        "nombre_wa": (nombre or None), "conocido": conocido,
        "contacto_crm_id": contacto_crm_id,
        "created_at": _now(), "updated_at": _now(),
    })
    if created:
        return created[0]
    rows = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero_id}", "wa_id": f"eq.{wa_id}",
                                          "select": "*", "limit": "1"})
    return rows[0] if rows else {}


async def _get_o_crea_conversacion_core(user_id: str, numero_id: str, contacto_id: str,
                                        ia_default: bool = True, *, sb_get, _now, sb_post) -> dict:
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    # Un CONOCIDO del asesor (agenda del celular o historial previo) arranca con
    # la IA apagada: la recepcionista es para prospectos nuevos, no para caerle
    # en frío a un cliente de años. El asesor la puede prender en esa conversación.
    fila = {
        "user_id": user_id, "numero_id": numero_id, "contacto_id": contacto_id,
        "ai_enabled": ia_default,
        # Chat nuevo de un desconocido: nace en 'auto' (obedece el modo global
        # del número) y con la sesión de "cliente nuevo" abierta — es la
        # primera vez que este número escribe. Chat de un conocido: nace en
        # 'off' y el agente la enciende si quiere.
        "ia_modo": "auto" if ia_default else "off",
        "ia_sesion_nueva": bool(ia_default),
        "created_at": _now(), "last_message_at": _now(),
    }
    created = await sb_post("wa2_conversaciones", fila)
    if not created:
        # Migración pendiente (columnas nuevas ausentes): reintentar sin ellas
        # para que el webhook no pierda ni un mensaje.
        fila.pop("ia_modo", None)
        fila.pop("ia_sesion_nueva", None)
        created = await sb_post("wa2_conversaciones", fila)
    if created:
        return created[0]
    rows = await sb_get("wa2_conversaciones", {"contacto_id": f"eq.{contacto_id}", "select": "*", "limit": "1"})
    return rows[0] if rows else {}
