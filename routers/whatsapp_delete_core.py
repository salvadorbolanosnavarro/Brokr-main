from __future__ import annotations


async def wa2_borrar_mensaje_core(mensaje_id: str, request, *, _require_user, _ids_visibles,
                                  sb_get, _in_filter, HTTPException, _borrar_archivos,
                                  sb_delete):
    """Borra UN mensaje de la bandeja (y su archivo, si lo tenía).

    Esto no existía. Sin esto, cuando un prospecto ejerce su derecho de
    cancelación —o cuando manda sin que nadie se lo pida una foto de su INE o
    un audio con datos delicados— el agente no tenía absolutamente ninguna
    forma de sacar eso de Broquer. El plazo del artículo 31 de la LFPDPPP le
    corría encima sin poder cumplir.

    Nota: solo borra la copia de Broquer. El mensaje sigue existiendo en el
    WhatsApp de las dos personas; eso no lo controla nadie más que ellas."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids),
                                         "select": "id,media_path", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    await _borrar_archivos([rows[0].get("media_path")])
    if not await sb_delete("wa2_mensajes", {"id": f"eq.{mensaje_id}", "user_id": _in_filter(ids)}):
        raise HTTPException(status_code=500, detail="No se pudo borrar el mensaje. Intenta de nuevo.")
    return {"ok": True}


async def wa2_borrar_conversacion_core(conversacion_id: str, request, *, _require_user,
                                       _ids_visibles, sb_get, _in_filter, HTTPException,
                                       _borrar_archivos, sb_delete, log):
    """Borra una conversación completa: sus mensajes, sus archivos y la ficha
    del prospecto en WhatsApp. El Contacto del CRM NO se toca — ese es un
    registro aparte que el agente decide si conserva o no desde Contactos."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                               "select": "id,contacto_id", "limit": "1"})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    archivos, pagina = [], 0
    while pagina < 40:
        lote = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}",
                                             "select": "media_path", "limit": "1000",
                                             "offset": str(pagina * 1000)})
        archivos.extend(m.get("media_path") for m in lote)
        if len(lote) < 1000:
            break
        pagina += 1
    await _borrar_archivos(archivos)

    await sb_delete("wa2_mensajes", {"conversacion_id": f"eq.{conversacion_id}"})
    try:
        await sb_delete("wa2_flujo_estados", {"conversacion_id": f"eq.{conversacion_id}"})
    except Exception:
        pass
    await sb_delete("wa2_conversaciones", {"id": f"eq.{conversacion_id}"})
    if conv[0].get("contacto_id"):
        await sb_delete("wa2_contactos", {"id": f"eq.{conv[0]['contacto_id']}"})
    log.info("Conversación %s eliminada por el usuario %s", conversacion_id, user_id)
    return {"ok": True}
