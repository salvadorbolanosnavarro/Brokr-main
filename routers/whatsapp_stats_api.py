"""Read-only WhatsApp statistics endpoint core."""
from __future__ import annotations


async def wa2_estadisticas_core(request, zona: str | None = None, *,
                                _require_user, _ids_visibles, _in_filter,
                                _ZONA_DEFAULT, asyncio, _sb_diag, _sb_get_paginado,
                                log, datetime, timezone, _agrega_ventana,
                                _VENTANAS_ESTAD, _now):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    filtro = _in_filter(ids)
    zona = zona or _ZONA_DEFAULT

    # Las tablas chicas se piden con select=* a propósito: si una columna
    # opcional todavía no existe en la base del agente (una migración que no se
    # corrió), un select con nombres explícitos devuelve 400 y TODO se ve en
    # cero sin decir por qué. Con * no hay columna que pueda faltar.
    (numeros, e_num), (contactos, e_con), (conversaciones, e_conv), (mensajes, e_msg) = await asyncio.gather(
        _sb_diag("wa2_numeros", {"user_id": filtro, "select": "*"}),
        _sb_get_paginado("wa2_contactos", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado("wa2_conversaciones", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado("wa2_mensajes", {
            "user_id": filtro, "order": "id.asc",
            "select": "conversacion_id,direction,sender,created_at"}),
    )
    # Respaldo: si el select angosto de mensajes falló (nombre de columna
    # distinto), se reintenta con * antes de darse por vencido.
    if e_msg and not mensajes:
        mensajes, e_msg2 = await _sb_get_paginado(
            "wa2_mensajes", {"user_id": filtro, "order": "id.asc", "select": "*"})
        if mensajes:
            e_msg = ""
        else:
            e_msg = e_msg2 or e_msg

    for n in numeros:
        n.pop("access_token", None)

    diagnostico = {
        "user_ids": len(ids),
        "numeros": len(numeros), "contactos": len(contactos),
        "conversaciones": len(conversaciones), "mensajes": len(mensajes),
        "errores": {k: v for k, v in {
            "wa2_numeros": e_num, "wa2_contactos": e_con,
            "wa2_conversaciones": e_conv, "wa2_mensajes": e_msg,
        }.items() if v},
    }
    if diagnostico["errores"]:
        log.error("estadisticas whatsapp2: %s", diagnostico["errores"])

    ahora = datetime.now(timezone.utc)
    ventanas = {
        nombre: _agrega_ventana(dias, ahora, zona, contactos, conversaciones, mensajes, numeros)
        for nombre, dias in _VENTANAS_ESTAD.items()
    }
    return {
        "ok": True,
        "zona": zona,
        "generado": _now(),
        "numeros_conectados": len(numeros),
        "diagnostico": diagnostico,
        "ventanas": ventanas,
    }
