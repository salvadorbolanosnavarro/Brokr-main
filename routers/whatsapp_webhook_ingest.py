"""Exact inbound WhatsApp webhook persistence core.

Behavior-preserving extraction from whatsapp.py. Dependencies are injected so
legacy wrappers and monkeypatch semantics remain under whatsapp.py.
"""

async def _persistir_entrantes_core(
    payload: dict, *, _get_numero, log, _solo_digitos, sb_get, _es_asesor,
    _get_o_crea_contacto, _get_o_crea_conversacion, _guardar_mensaje,
    _entrenamiento_de, _pausar_por_respuesta_manual, sb_patch, _now,
    _agenda_upsert, datetime, timezone, _descargar_media, _transcribir_audio,
    _describir_imagen, re, _guardar_archivo, _OPT_OUT_PALABRAS,
    _revisar_token, enviar_push,
):
    trabajo = []
    entradas = payload.get("entry", [])
    if not entradas:
        log.warning("Webhook 2.0 sin 'entry' — claves del payload: %s", sorted(payload.keys()))
    for entry in entradas:
        cambios = entry.get("changes", [])
        if not cambios:
            log.warning("Webhook 2.0 sin 'changes' en entry %s", entry.get("id"))
        for change in cambios:
            val = change.get("value", {})
            phone_number_id = (val.get("metadata") or {}).get("phone_number_id")
            if not phone_number_id:
                # Antes esto era un `continue` mudo — no había forma de saber si
                # llegó un evento sin phone_number_id (ej. otro field distinto a
                # "messages") o si el payload traía una forma inesperada.
                log.warning("Webhook 2.0 sin phone_number_id (field=%s, claves de value=%s) — ignorado",
                           change.get("field"), sorted(val.keys()))
                continue
            numero = await _get_numero(phone_number_id)
            if not numero:
                log.warning("Número no registrado en wa2_numeros: %s — ignorado", phone_number_id)
                continue
            contactos_meta = {c["wa_id"]: c.get("profile", {}).get("name") for c in val.get("contacts", [])}

            # ── COEXISTENCIA: ecos de lo que el asesor manda DESDE SU CELULAR ──
            # Cuando el número coexiste con la app de WhatsApp Business, lo que
            # el asesor contesta desde su teléfono llega aquí como message_echoes
            # (campo smb_message_echoes). Sin esto Broquer nunca se enteraba de
            # que el asesor ya respondió y la IA le contestaba ENCIMA al mismo
            # prospecto. El eco se guarda en la bandeja como mensaje del agente
            # y apaga la IA de esa conversación, igual que el envío manual.
            entren_eco = None  # se carga una sola vez si hay ecos que pausar
            for eco in (val.get("message_echoes") or []):
                wa_dest = _solo_digitos(eco.get("to") or "")
                if not wa_dest:
                    continue
                ya = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{eco.get('id')}",
                                                   "select": "id", "limit": "1"})
                if ya:
                    continue
                if eco.get("type") == "text":
                    cuerpo = (eco.get("text") or {}).get("body", "")
                else:
                    cuerpo = f"[{eco.get('type') or 'mensaje'} enviado por el asesor desde su celular]"
                # Eco hacia el NÚMERO PERSONAL del asesor: es él mismo
                # tecleando desde su celular de negocio dentro de su chat con
                # Broq. Se guarda para que la conversación quede completa, pero
                # NO es un comando (los comandos son los que MANDA desde su
                # número personal y llegan como entrantes) — Broq no responde
                # a esto ni se dispara la lógica de pausa/conocidos.
                if _es_asesor(numero, wa_dest):
                    contacto_self = await _get_o_crea_contacto(numero["user_id"], numero["id"],
                                                               wa_dest, "Tú · Broq", crear_crm=False)
                    if not contacto_self:
                        continue
                    conv_self = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                               contacto_self["id"], ia_default=False)
                    await _guardar_mensaje(numero["user_id"], contacto_self["id"], conv_self["id"],
                                          eco.get("id"), "out", "agente", cuerpo)
                    continue

                contacto_eco = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_dest, None)
                if not contacto_eco:
                    continue
                conv_eco = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          contacto_eco["id"], ia_default=False)
                await _guardar_mensaje(numero["user_id"], contacto_eco["id"], conv_eco["id"],
                                      eco.get("id"), "out", "agente", cuerpo)
                # El asesor contestó desde su celular: la IA se hace a un
                # lado según la config del número (pausa temporal o para
                # siempre), exactamente igual que al escribir desde Broquer.
                if entren_eco is None:
                    entren_eco = await _entrenamiento_de(numero["user_id"], numero["id"])
                await _pausar_por_respuesta_manual(conv_eco, numero, entren_eco)
                if not contacto_eco.get("conocido"):
                    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_eco['id']}"},
                                   {"conocido": True, "updated_at": _now()})
                    await _agenda_upsert(numero["user_id"], numero["id"], wa_dest, conocido=True)

            # ── COEXISTENCIA: agenda del celular del asesor ────────────────────
            # Meta sincroniza los contactos del teléfono (smb_app_state_sync).
            # Ese nombre — el que el asesor le puso a la persona en SU agenda —
            # es la fuente correcta para nombrar leads en Broquer; el nombre que
            # el lead se puso a sí mismo en WhatsApp es el último recurso.
            for sync in (val.get("state_sync") or []):
                if sync.get("type") != "contact":
                    continue
                cont_s = sync.get("contact") or {}
                tel_s = _solo_digitos(cont_s.get("phone_number") or "")
                nombre_s = (cont_s.get("full_name") or cont_s.get("first_name") or "").strip()
                if not tel_s or (sync.get("action") or "add") == "remove":
                    continue
                await _agenda_upsert(numero["user_id"], numero["id"], tel_s, nombre=nombre_s or None)
                filas_c = await sb_get("wa2_contactos", {"numero_id": f"eq.{numero['id']}",
                                                         "wa_id": f"eq.{tel_s}",
                                                         "select": "*", "limit": "1"})
                if filas_c and nombre_s:
                    c0 = filas_c[0]
                    cambios_c = {"nombre_agenda": nombre_s, "updated_at": _now()}
                    # El nombre de agenda solo manda si el lead no se ha
                    # presentado él mismo en el chat (esa es la prioridad 1).
                    if not (c0.get("nombre_chat") or "").strip():
                        cambios_c["nombre"] = nombre_s
                    await sb_patch("wa2_contactos", {"id": f"eq.{c0['id']}"}, cambios_c)

            # ── COEXISTENCIA: historial de chats previos a la conexión ─────────
            # En el onboarding Meta manda los chats que el número ya tenía
            # (campo history). No se importan esos mensajes: solo sirve para
            # marcar a esas personas como CONOCIDAS del asesor, para que la
            # recepcionista jamás les caiga en frío como a un prospecto nuevo.
            for bloque_h in (val.get("history") or []):
                for hilo in (bloque_h.get("threads") or []):
                    tel_h = _solo_digitos(str(hilo.get("id") or ""))
                    if tel_h:
                        await _agenda_upsert(numero["user_id"], numero["id"], tel_h, conocido=True)

            for msg in val.get("messages", []):
                wa_id = msg.get("from")
                if not wa_id:
                    continue

                # SEGURIDAD: nunca proceses ni respondas mensajes de ANTES de
                # que el número se conectara a Broquer. Meta puede reenviar
                # eventos de mensajes viejos (coexistencia con un número que
                # ya tenía historial, reintentos de webhook, etc.) y sin este
                # filtro la IA le contestaría a un mensaje de hace semanas
                # como si fuera de ahorita — sin que el agente lo autorizara.
                try:
                    msg_ts = int(msg.get("timestamp") or 0)
                    creado_en = numero.get("created_at")
                    if msg_ts and creado_en:
                        creado_dt = datetime.fromisoformat(creado_en.replace("Z", "+00:00"))
                        if datetime.fromtimestamp(msg_ts, timezone.utc) < creado_dt:
                            log.warning("Mensaje anterior a la conexión del número %s — ignorado (%s)",
                                       numero.get("phone_number_id"), msg.get("id"))
                            continue
                except Exception:
                    pass

                # La revisión de duplicados va ANTES de tocar la media: Meta
                # reenvía el mismo webhook cuando no le contestamos rápido, y
                # transcribir dos veces la misma nota de voz se paga dos veces.
                existe = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{msg.get('id')}",
                                                       "select": "id", "limit": "1"})
                if existe:
                    continue

                tipo_msg = msg.get("type")
                texto = ""
                media_bytes: bytes | None = None
                media_mime = ""
                media_sufijo = "archivo"
                if tipo_msg == "text":
                    texto = (msg.get("text") or {}).get("body", "")
                elif tipo_msg in ("audio", "voice"):
                    # Nota de voz: se oye de verdad. Antes se guardaba "[audio]"
                    # y la IA le contestaba al prospecto sin tener idea de lo
                    # que le dijo — la peor tontería posible frente a un cliente.
                    media_id = (msg.get(tipo_msg) or {}).get("id")
                    media_bytes, media_mime = await _descargar_media(numero, media_id)
                    media_sufijo = "nota-de-voz"
                    dicho = await _transcribir_audio(media_bytes, media_mime) if media_bytes else ""
                    texto = f"[nota de voz] {dicho}" if dicho else \
                        "[nota de voz que no se pudo transcribir]"
                elif tipo_msg == "image":
                    media_id = (msg.get("image") or {}).get("id")
                    pie = (msg.get("image") or {}).get("caption") or ""
                    media_bytes, media_mime = await _descargar_media(numero, media_id)
                    media_sufijo = "foto"
                    visto = await _describir_imagen(media_bytes, media_mime) if media_bytes else ""
                    texto = "[foto] " + " ".join(x for x in [pie, visto] if x).strip()
                    if not visto and not pie:
                        texto = "[foto que no se pudo leer]"
                elif tipo_msg == "location":
                    loc = msg.get("location") or {}
                    partes_loc = [loc.get("name"), loc.get("address"),
                                  f"{loc.get('latitude')},{loc.get('longitude')}"]
                    texto = "[ubicación] " + " · ".join(str(x) for x in partes_loc if x)
                elif tipo_msg == "document":
                    doc = msg.get("document") or {}
                    media_bytes, media_mime = await _descargar_media(numero, doc.get("id"))
                    media_sufijo = re.sub(r"[^A-Za-z0-9._-]", "_", (doc.get("filename") or "documento"))[:60]
                    texto = f"[documento] {doc.get('filename') or ''} {doc.get('caption') or ''}".strip()
                elif tipo_msg == "video":
                    vid = msg.get("video") or {}
                    media_bytes, media_mime = await _descargar_media(numero, vid.get("id"))
                    media_sufijo = "video"
                    texto = f"[video] {vid.get('caption') or ''}".strip()
                elif tipo_msg == "contacts":
                    texto = "[el prospecto compartió una tarjeta de contacto]"
                elif tipo_msg in ("button", "interactive"):
                    inter = msg.get("interactive") or {}
                    texto = ((msg.get("button") or {}).get("text")
                             or (inter.get("button_reply") or {}).get("title")
                             or (inter.get("list_reply") or {}).get("title")
                             or "[respuesta a un botón]")
                else:
                    texto = f"[mensaje de tipo {tipo_msg or 'desconocido'}]"

                es_asesor = _es_asesor(numero, wa_id)
                if es_asesor:
                    # Escribe el DUEÑO desde su número personal registrado: es
                    # una orden para Broq (modo asesor), nunca un prospecto.
                    contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                          "Tú · Broq", crear_crm=False)
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          contacto["id"], ia_default=False)
                else:
                    contacto = await _get_o_crea_contacto(numero["user_id"], numero["id"], wa_id,
                                                          contactos_meta.get(wa_id))
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"], contacto["id"],
                                                         ia_default=not contacto.get("conocido"))

                media_url, media_path = (None, None)
                if media_bytes:
                    media_url, media_path = await _guardar_archivo(
                        numero["user_id"], conv["id"], media_bytes, media_mime, media_sufijo)

                await _guardar_mensaje(numero["user_id"], contacto["id"], conv["id"], msg.get("id"),
                                      "in", "agente" if es_asesor else "lead", texto, media_url, media_path)
                if not es_asesor:
                    await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"},
                                  {"unread_count": (conv.get("unread_count") or 0) + 1})

                # ── BAJA de campañas por palabra clave (opt-out) ──────────
                # Si el mensaje ES exactamente una palabra de baja, el
                # contacto queda fuera de todas las campañas para siempre.
                # Nunca truena el webhook: si la columna no existe todavía
                # (migración pendiente), simplemente no pasa nada.
                if (not es_asesor and tipo_msg == "text"
                        and texto.strip().lower().rstrip(".!") in _OPT_OUT_PALABRAS):
                    try:
                        await sb_patch("wa2_contactos", {"id": f"eq.{contacto['id']}"},
                                       {"opt_out": True, "updated_at": _now()})
                    except Exception:
                        pass

                trabajo.append({"numero": numero, "contacto_id": contacto["id"],
                               "conversacion_id": conv["id"], "wa_id": wa_id, "texto": texto,
                               "wa_message_id": msg.get("id"), "es_asesor": es_asesor,
                               # Cuándo había escrito ANTES de este mensaje (ya con el
                               # mensaje guardado, last_inbound_at apunta a ahorita y no
                               # serviría para saber si es un cliente nuevo).
                               "prev_inbound_at": conv.get("last_inbound_at")})

            # ── Acuses de Meta (enviado / entregado / leído / FALLIDO) ──────
            # Esto se ignoraba por completo. Lo grave no es perderse la
            # palomita: es que cuando Meta RECHAZA un mensaje (número dado de
            # baja, plantilla no aprobada, ventana cerrada, límite de la
            # cuenta) el agente creía que su mensaje salió y nunca salió.
            for st in val.get("statuses", []):
                estado = st.get("status")
                if estado != "failed":
                    continue
                errs = st.get("errors") or [{}]
                err0 = errs[0] if errs else {}
                log.error("Mensaje NO entregado (%s): %s %s",
                          numero.get("phone_number_id"), err0.get("code"), err0.get("title"))
                await _revisar_token(numero, {"code": err0.get("code"),
                                              "message": err0.get("title") or ""})
                try:
                    await sb_patch("wa2_mensajes", {"wa_message_id": f"eq.{st.get('id')}"},
                                   {"entrega_error": (err0.get("title") or "No se pudo entregar")[:200]})
                except Exception:
                    pass
                await enviar_push(numero.get("user_id"), "Un mensaje no se pudo entregar",
                                  err0.get("title") or "WhatsApp rechazó el envío. Revisa la conversación.",
                                  datos={"tipo": "whatsapp"})
    return True, trabajo
