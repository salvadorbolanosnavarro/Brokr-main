"""WhatsApp advisor-mode Anthropic orchestration."""
from __future__ import annotations


async def _broq_asesor_core(item: dict, numero: dict, user_id: str, *,
                            _entrenamiento_de, sb_get, HISTORY_LIMIT,
                            _fmt_fecha_larga, _hora_local, httpx,
                            ANTHROPIC_BASE, ANTHROPIC_API_KEY, WA2_MODEL,
                            ASESOR_TOOLS, log, _asesor_ejecutar_tool,
                            _wa_send_text, _guardar_mensaje):
    entren = await _entrenamiento_de(user_id, numero["id"])
    zona = entren.get("zona_horaria")

    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}",
                                                    "select": "asesor_ctx", "limit": "1"})
    ctx = (conv_rows[0].get("asesor_ctx") or {}) if conv_rows else {}
    ctx_txt = ""
    if ctx:
        partes_ctx = []
        if ctx.get("ultima_tarea_id"):
            partes_ctx.append(f"la última tarea creada o tocada es id={ctx['ultima_tarea_id']} "
                              f"('{ctx.get('ultima_tarea_titulo') or ''}')")
        for d in ("contacto", "propiedad", "tarea"):
            if ctx.get(f"ultimo_{d}_id"):
                partes_ctx.append(f"el último {d} tocado es id={ctx[f'ultimo_{d}_id']} "
                                  f"('{ctx.get(f'ultimo_{d}_nombre') or ''}')")
        if partes_ctx:
            ctx_txt = ("\nMEMORIA DE ESTA CHARLA: " + "; ".join(partes_ctx) +
                       ". Cuando el asesor diga 'esa misma tarea', 'ese contacto', 'esa casa', "
                       "usa ESTOS ids directo, sin volver a buscar.")

    hist = await sb_get("wa2_mensajes", {"conversacion_id": f"eq.{item['conversacion_id']}",
                                         "select": "direction,body",
                                         "order": "created_at.desc", "limit": str(HISTORY_LIMIT)})
    hist.reverse()
    crudos = [{"role": "user" if m.get("direction") == "in" else "assistant",
               "content": m.get("body") or ""} for m in hist if (m.get("body") or "").strip()]
    while crudos and crudos[0]["role"] != "user":
        crudos.pop(0)
    if not crudos:
        crudos = [{"role": "user", "content": item["texto"]}]
    # Mensajes seguidos del mismo lado se funden en uno: la API exige turnos.
    messages: list = []
    for m in crudos:
        if messages and messages[-1]["role"] == m["role"] and isinstance(messages[-1]["content"], str):
            messages[-1]["content"] += "\n" + m["content"]
        else:
            messages.append(dict(m))

    system = (
        "Eres Broq, el asistente personal del asesor inmobiliario DENTRO de su propio WhatsApp. "
        "Quien te escribe es EL ASESOR dueño del número (NO un cliente): te escribe desde su número "
        "personal, por texto o nota de voz, para dictarte acciones rápidas en Broquer.\n"
        f"Hoy es {_fmt_fecha_larga(_hora_local(zona))}. Español mexicano, directo, mensajes cortos de "
        "WhatsApp, sin emojis.\n"
        "Tus herramientas: buscar contactos, tareas y propiedades; agregar comentarios con fecha a un "
        "contacto, una tarea o una propiedad; y crear tareas nuevas (con vínculo opcional a un contacto "
        "y/o inmueble). Antes de agregar un comentario o vincular algo, BUSCA para usar el id exacto; si "
        "varios coinciden, pregunta cuál en una línea. Si no encuentras nada, dilo tal cual — NUNCA "
        "inventes contactos, tareas, propiedades ni ids. NUNCA digas que algo quedó registrado si el "
        "resultado de la herramienta no lo confirmó.\n"
        "Después de ejecutar, confirma en UNA línea qué quedó registrado y EN QUIÉN o EN QUÉ (el nombre "
        "viene en el tool_result). Si el asesor pide algo fuera de tus herramientas, dile que eso se hace "
        "en la app de Broquer y en qué módulo."
        + ctx_txt
    )

    reply = ""
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            for _vuelta in range(6):
                r = await c.post(f"{ANTHROPIC_BASE}/messages",
                                 headers={"x-api-key": ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01",
                                          "Content-Type": "application/json"},
                                 json={"model": WA2_MODEL, "max_tokens": 900, "system": system,
                                       "messages": messages, "tools": ASESOR_TOOLS})
                if r.status_code != 200:
                    log.error("Modo asesor: Anthropic %s %s", r.status_code, r.text[:200])
                    break
                data = r.json()
                content = data.get("content", []) or []
                texto_turno = "".join(b.get("text", "") for b in content
                                      if b.get("type") == "text").strip()
                if texto_turno:
                    reply = texto_turno
                if data.get("stop_reason") != "tool_use":
                    break
                messages.append({"role": "assistant", "content": content})
                resultados = []
                for b in content:
                    if b.get("type") != "tool_use":
                        continue
                    try:
                        res = await _asesor_ejecutar_tool(user_id, b.get("name"),
                                                          b.get("input") or {}, zona,
                                                          item["conversacion_id"])
                    except Exception as e:
                        res = f"La herramienta falló: {str(e)[:120]}"
                    resultados.append({"type": "tool_result", "tool_use_id": b.get("id"),
                                       "content": res})
                messages.append({"role": "user", "content": resultados})
    except Exception as e:
        log.exception("Modo asesor reventó: %s", e)

    if not reply:
        reply = "No pude procesar tu instrucción ahorita. Mándamela de nuevo en un momento."
    wamid = await _wa_send_text(numero, item["wa_id"], reply)
    await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"], wamid,
                          "out", "ia", reply)
