from __future__ import annotations


async def _responder_conversacion_core(item: dict, numero: dict, user_id: str, *,
                                       sb_get, _entrenamiento_de, _parse_ts, datetime,
                                       timezone, sb_patch, _ia_decide, _en_horario,
                                       _wa_marcar_leido, _wa_send_text, _guardar_mensaje,
                                       enviar_push, WA2_TOPE_IA, HISTORY_LIMIT,
                                       _perfil_agente, recepcion2_responde, _now,
                                       _sincronizar_contacto_crm, _parsear_presupuesto,
                                       _buscar_inmuebles, asyncio, _generar_ficha_pdf,
                                       _propiedad_para_ficha, _texto_inmueble,
                                       _wa_send_document_link, _resolver_inmueble_id,
                                       sb_post, _fecha_hora_utc_iso, _construir_ics,
                                       _wa_send_document, _alta_inmueble, log, _money):
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}", "select": "*", "limit": "1"})
    conv = conv_rows[0] if conv_rows else {}
    contacto_rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}", "select": "*", "limit": "1"})
    contacto = contacto_rows[0] if contacto_rows else {}

    # (El aviso al celular ya se mandó en _procesar_en_segundo_plano.)

    entren = await _entrenamiento_de(user_id, numero["id"])
    if not entren.get("activo", True):
        return

    # ── Sesión de "cliente nuevo" (para el modo global "solo_nuevos") ──────
    # Cliente nuevo = número que nunca había escrito, o que llevaba más de
    # `nuevos_meses` sin escribir. La sesión se abre aquí y se cierra en
    # cuanto el agente responde a mano (el chat ya es suyo).
    if "prev_inbound_at" in item and not conv.get("ia_sesion_nueva"):
        prev_dt = _parse_ts(item.get("prev_inbound_at"))
        try:
            meses = int(entren.get("nuevos_meses") or 3)
        except Exception:
            meses = 3
        if prev_dt is None or (datetime.now(timezone.utc) - prev_dt).days >= meses * 30:
            conv["ia_sesion_nueva"] = True
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ia_sesion_nueva": True})

    if not _ia_decide(conv, entren, numero):
        return  # el humano tiene el control (modo del chat, pausa o modo global)
    if not _en_horario(entren):
        msg_fuera = entren.get("fuera_horario_msg") or "Gracias por tu mensaje, en cuanto abramos te contesto."
        await _wa_marcar_leido(numero, item.get("wa_message_id"))
        wamid = await _wa_send_text(numero, item["wa_id"], msg_fuera)
        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                              "out", "ia", msg_fuera)
        return

    palabras = entren.get("escalar_palabras") or []
    if isinstance(palabras, str):
        palabras = [p.strip() for p in palabras.split(",") if p.strip()]
    if any(p.lower() in item["texto"].lower() for p in palabras if p):
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "Un prospecto pidió hablar contigo",
                          f"{contacto.get('nombre') or item['wa_id']}: {item['texto'][:100]}",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # El tope del entrenamiento manda solo si es MÁS estricto que el tope duro.
    # Un 0 guardado (que antes significaba "ilimitado") ahora cae al tope duro.
    max_msj = entren.get("max_mensajes_ia") or 0
    if max_msj <= 0 or max_msj > WA2_TOPE_IA:
        max_msj = WA2_TOPE_IA
    conteo = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{item['conversacion_id']}",
                                           "sender": "eq.ia", "select": "id"})
    if len(conteo) >= max_msj:
        # Antes esto apagaba la IA y se salía en silencio: el prospecto se
        # quedaba escribiendo al vacío y el agente nunca se enteraba de que
        # ahora le tocaba a él. Ahora se le avisa.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "Un prospecto te está esperando",
                          f"{contacto.get('nombre') or item['wa_id']} lleva rato platicando con la IA. "
                          "Ya te toca a ti seguir la conversación.",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # Ya se decidió que la IA sí va a contestar: hasta ahora se vale poner la
    # palomita azul y el "escribiendo…" del lado del prospecto.
    await _wa_marcar_leido(numero, item.get("wa_message_id"))

    historial_rows = await sb_get("wa2_mensajes", {
        "conversacion_id": f"eq.{item['conversacion_id']}", "select": "sender,body",
        "order": "created_at.desc", "limit": str(HISTORY_LIMIT)})
    historial_rows.reverse()
    history = [{"role": "assistant" if m["sender"] in ("ia", "agente") else "user", "content": m.get("body") or ""}
              for m in historial_rows]

    agente = await _perfil_agente(user_id)
    contexto = conv.get("property_ctx") or (
        f"Atiendes prospectos de {agente['nombre']}, asesor inmobiliario"
        f"{(' en ' + agente['zona']) if agente['zona'] else ''}. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca.")

    resultado = await recepcion2_responde(history, contexto, agente, entren)

    reply = resultado.get("reply") or "Gracias por tu mensaje."
    wamid = await _wa_send_text(numero, item["wa_id"], reply)
    await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid, "out", "ia", reply)

    if resultado.get("_falla_tecnica"):
        # La IA no pudo pensar la respuesta (la API venía caída o saturada).
        # Se le pasa la conversación al humano y se le avisa: un prospecto
        # esperando a un bot descompuesto es un prospecto perdido.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                       {"ai_enabled": False, "ia_modo": "off"})
        await enviar_push(user_id, "La IA no pudo contestar",
                          f"{contacto.get('nombre') or item['wa_id']} está esperando respuesta. "
                          "Entra a la conversación tú.",
                          datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
        return

    # Actualiza la ficha del prospecto con lo que la IA acaba de calificar
    notas_actuales = contacto.get("notas") or []
    if resultado.get("nota"):
        notas_actuales = notas_actuales + [{"texto": resultado["nota"], "autor": "ia", "fecha": _now()}]
    # El nombre con el que el prospecto SE PRESENTÓ en el chat es la prioridad 1
    # (arriba de la agenda del celular y del nombre de WhatsApp).
    nombre_chat = (resultado.get("nombre") or "").strip() or (contacto.get("nombre_chat") or "").strip()
    update_contacto = {
        "temperatura": resultado.get("temperatura") or contacto.get("temperatura") or "Nuevo",
        "score": resultado.get("score") if resultado.get("score") is not None else contacto.get("score", 0),
        "presupuesto": resultado.get("presupuesto") or contacto.get("presupuesto"),
        "forma_pago": resultado.get("forma_pago") or contacto.get("forma_pago"),
        "busca": resultado.get("busca") or contacto.get("busca"),
        "resumen": resultado.get("resumen") or contacto.get("resumen"),
        "notas": notas_actuales,
        "updated_at": _now(),
    }
    if nombre_chat:
        update_contacto["nombre_chat"] = nombre_chat
        update_contacto["nombre"] = nombre_chat
    await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, update_contacto)
    await _sincronizar_contacto_crm(user_id, dict(contacto, **update_contacto), resultado)

    accion = resultado.get("accion")
    if isinstance(accion, dict):
        tipo = accion.get("tipo")
        if tipo == "enviar_inmuebles":
            filtros_ia = accion.get("filtros") or {}
            if not filtros_ia.get("precio_max"):
                # Respaldo: la IA no mandó precio_max en esta acción, pero si
                # el prospecto ya dio su presupuesto antes (queda en su ficha),
                # se usa de todos modos — no se le ofrece algo fuera de su rango
                # solo porque el mensaje más reciente no repitió el monto.
                respaldo = _parsear_presupuesto(resultado.get("presupuesto") or contacto.get("presupuesto") or "")
                if respaldo:
                    filtros_ia = {**filtros_ia, "precio_max": respaldo}
            props, zona_sin_resultados = await _buscar_inmuebles(user_id, filtros_ia)
            if props:
                enviados = []
                # Las fichas se arman EN PARALELO. En serie eran hasta 45
                # segundos por cada una: el prospecto leía "ahorita te las
                # comparto" y las recibía dos minutos y medio después, cuando
                # ya se había ido a otro anuncio.
                fichas = await asyncio.gather(
                    *[_generar_ficha_pdf(_propiedad_para_ficha(p)) for p in props[:3]],
                    return_exceptions=True)
                for idx, p in enumerate(props[:3]):
                    # Antes se mandaba foto+texto Y la ficha técnica (redundante,
                    # la ficha ya trae fotos y datos). Ahora solo la ficha.
                    resumen = _texto_inmueble(p).replace("\n", " · ")
                    ficha = fichas[idx] if idx < len(fichas) else None
                    url_pdf, filename = ficha if isinstance(ficha, tuple) else (None, None)
                    if url_pdf:
                        wamid = await _wa_send_document_link(
                            numero, item["wa_id"], url_pdf, filename or "ficha.pdf", resumen)
                        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                                              "out", "ia", f"[ficha técnica] {resumen}", url_pdf)
                    else:
                        # Si por lo que sea no se pudo armar el PDF a tiempo, que
                        # al menos le llegue la info en texto, no que no reciba nada.
                        wamid = await _wa_send_text(numero, item["wa_id"], _texto_inmueble(p))
                        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                                              "out", "ia", _texto_inmueble(p))
                    enviados.append({"id": p.get("id"), "titulo": p.get("titulo") or p.get("tipo") or "propiedad"})
                # Se recuerdan aquí (no en el historial de mensajes) para poder
                # adjuntar la propiedad correcta a la tarea si más adelante agenda una visita.
                await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                              {"ultimas_propiedades": enviados})
            elif zona_sin_resultados:
                # De verdad no hay nada en la zona que pidió: se le dice tal
                # cual, NUNCA se le manda una propiedad de otra ubicación
                # como si fuera lo que preguntó.
                zona_txt = (filtros_ia.get("colonia") or filtros_ia.get("zona_amplia")
                           or filtros_ia.get("ciudad") or "esa zona").strip()
                aviso = (f"Por ahora no tengo nada disponible en {zona_txt}. "
                         "Le aviso a mi asesor para que revise si tiene algo que no esté "
                         "publicado, o si prefieres te comparto opciones en otra zona cercana.")
                wamid2 = await _wa_send_text(numero, item["wa_id"], aviso)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid2, "out", "ia", aviso)
                await enviar_push(user_id, "Un prospecto busca algo que no tienes publicado",
                                  f"{contacto.get('nombre') or item['wa_id']} pidió {zona_txt} y no hay inventario ahí.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            else:
                aviso = "Por ahora no tengo una opción exacta, pero le aviso a mi asesor para que te comparta algo a la medida."
                wamid2 = await _wa_send_text(numero, item["wa_id"], aviso)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid2, "out", "ia", aviso)

        elif tipo == "agendar_visita":
            fecha = accion.get("fecha"); hora = accion.get("hora")
            if fecha and hora:
                nombre_prospecto = contacto.get("nombre") or item["wa_id"]
                inmueble_txt = (accion.get("inmueble") or "").strip()
                titulo = f"Visita con {nombre_prospecto} (WhatsApp)"
                if inmueble_txt:
                    titulo += f" — {inmueble_txt}"
                crm_id = contacto.get("contacto_crm_id")
                propiedad_id = _resolver_inmueble_id(inmueble_txt, conv.get("ultimas_propiedades") or [])
                creada = await sb_post("tareas", {
                    "user_id": user_id, "titulo": titulo,
                    "fecha_entrega": _fecha_hora_utc_iso(fecha, hora, entren.get("zona_horaria")),
                    "notas": inmueble_txt or None,
                    "propiedad_id": propiedad_id,
                    "contacto_id": crm_id})
                if creada and crm_id:
                    await sb_post("tareas_contactos", {
                        "user_id": user_id, "tarea_id": creada[0]["id"], "contacto_id": crm_id})
                if creada and propiedad_id:
                    await sb_post("tareas_propiedades", {
                        "user_id": user_id, "tarea_id": creada[0]["id"], "propiedad_id": propiedad_id})
                await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"}, {"etapa": "Cita"})
                ics = _construir_ics(fecha, hora, titulo, inmueble_txt, entren.get("zona_horaria"))
                await _wa_send_document(numero, item["wa_id"], ics.encode("utf-8"),
                                       "cita.ics", "Toca el archivo para agregarla a tu calendario.")
                await enviar_push(user_id, "Nueva cita agendada",
                                  f"{nombre_prospecto} — {fecha} {hora} (revísala en Tareas)",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

        elif tipo == "registrar_inmueble":
            datos = accion.get("datos") or {}
            # Se recuperan las fotos que el remitente mandó EN ESTA conversación
            # para adjuntarlas al inmueble. Ya viven en el almacenamiento de
            # Broquer, así que son ligas propias y permanentes.
            fotos_rows = await sb_get("wa2_mensajes", {
                "conversacion_id": f"eq.{item['conversacion_id']}", "direction": "eq.in",
                "media_url": "not.is.null", "select": "body,media_url",
                "order": "created_at.desc", "limit": "20"})
            fotos = [f["media_url"] for f in fotos_rows
                     if (f.get("body") or "").lower().startswith("[foto")]
            fotos.reverse()

            inmueble_id = await _alta_inmueble(user_id, datos, item["wa_id"], fotos)
            if inmueble_id:
                # Quien mandó el inmueble queda vinculado como su Propietario en
                # el CRM (contactos_propiedades), para que al abrirlo en Mis
                # Inmuebles se sepa de inmediato de quién es y cómo contactarlo.
                crm_id_prop = contacto.get("contacto_crm_id")
                if crm_id_prop:
                    vinculo = await sb_post("contactos_propiedades", {
                        "user_id": user_id, "contacto_id": crm_id_prop,
                        "propiedad_id": inmueble_id, "relacion": "propietario"})
                    if not vinculo:
                        log.warning("No se pudo vincular al propietario %s con el inmueble %s",
                                    crm_id_prop, inmueble_id)
                # Al remitente NADA de promesas: un "gracias" y punto. Si se le
                # dijera "ya quedó registrada" creería que está publicada.
                gracias = "¡Muchas gracias!"
                wamid3 = await _wa_send_text(numero, item["wa_id"], gracias)
                await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                                       wamid3, "out", "ia", gracias)
                await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"},
                               {"etapa": "Propietario"})
                etiqueta = " · ".join(x for x in [datos.get("tipo"), datos.get("colonia"),
                                                  _money(datos.get("precio"))] if x)
                await enviar_push(user_id, "Te mandaron un inmueble",
                                  f"{contacto.get('nombre') or item['wa_id']}: {etiqueta or 'un inmueble'}. "
                                  "Quedó guardado como No activo — revísalo en Mis Inmuebles.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            else:
                await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                               {"ai_enabled": False, "ia_modo": "off"})
                await enviar_push(user_id, "No se pudo guardar un inmueble",
                                  f"{contacto.get('nombre') or item['wa_id']} te mandó una propiedad y "
                                  "no se pudo registrar. Entra a la conversación.",
                                  datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

        elif tipo == "pasar_a_humano":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ai_enabled": False, "ia_modo": "off"})
            await enviar_push(user_id, "Un prospecto necesita de ti",
                              accion.get("motivo") or "La IA te pasó esta conversación.",
                              datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
