from __future__ import annotations


async def wa2_enviar_manual_core(req, request, *, _require_user, _ids_visibles,
                                 sb_get, _in_filter, HTTPException, WA_MAX_TEXTO,
                                 _wa_send_text_detallado, _guardar_mensaje,
                                 _pausar_por_respuesta_manual):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "*", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]

    texto = (req.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="El mensaje viene vacío.")
    if len(texto) > WA_MAX_TEXTO:
        raise HTTPException(status_code=400,
            detail=f"El mensaje es demasiado largo ({len(texto)} caracteres). "
                   f"WhatsApp solo permite {WA_MAX_TEXTO}. Mándalo en dos partes.")

    wamid, error = await _wa_send_text_detallado(numero, contacto.get("wa_id"), texto)
    if error:
        if error.get("code") == 131047:
            raise HTTPException(status_code=409, detail={
                "ventana_cerrada": True,
                "mensaje": "Pasaron más de 24 horas desde el último mensaje del prospecto. "
                           "WhatsApp ya no deja mandar texto libre — usa una plantilla para reabrir la conversación.",
            })
        raise HTTPException(status_code=502, detail=error.get("message") or "No se pudo enviar el mensaje.")
    await _guardar_mensaje(conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", texto)

    # En cuanto el asesor escribe con sus propias manos, la IA se hace a un
    # lado en ESA conversación (para siempre o por el rato que él configuró
    # en Recepción IA). Si no, pasa lo más ridículo que puede pasar: el
    # prospecto contesta y le responden dos "personas" distintas, con
    # criterios distintos, en el mismo chat. Se reactiva con el control de IA.
    pausa = await _pausar_por_respuesta_manual(conv, numero)
    return {"ok": True, "ia_pausada": pausa["ia_pausada"],
            "ia_pausada_hasta": pausa["ia_pausada_hasta"],
            "para_siempre": pausa["para_siempre"]}


async def wa2_lectura_core(conversacion_id: str, req, request, *, _require_user,
                           _ids_visibles, sb_get, _in_filter, HTTPException,
                           sb_patch, _wa_marcar_leido):
    """Marca la conversación como leída o como NO leída, a mano.

    · no_leida=False → se pone en cero el contador y, ahora sí, se le manda la
      palomita azul al prospecto: alguien de verdad abrió su mensaje.
    · no_leida=True  → el agente la deja pendiente aunque ya la haya abierto,
      igual que en WhatsApp. La palomita azul que ya se mandó no se puede
      quitar (Meta no lo permite), pero en Broquer la conversación vuelve a
      aparecer sin leer.
    """
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "*", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]

    if req.no_leida:
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                       {"no_leida": True, "unread_count": max(1, int(conv.get("unread_count") or 0))})
        return {"ok": True, "no_leida": True}

    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                   {"no_leida": False, "unread_count": 0})

    # Palomita azul al prospecto, sin "escribiendo…": lo leyó un humano, no la IA.
    wamid = conv.get("last_inbound_wamid")
    if wamid:
        numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{conv.get('numero_id')}",
                                                   "select": "*", "limit": "1"})
        if numero_rows:
            await _wa_marcar_leido(numero_rows[0], wamid, escribiendo=False)

    return {"ok": True, "no_leida": False}
