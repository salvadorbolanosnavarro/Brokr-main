from __future__ import annotations


async def wa2_plantillas_list_core(request, numero_id: str, *, _require_user, _ids_visibles,
                                   sb_get, _in_filter, HTTPException, httpx, GRAPH_API, log):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                                "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        return {"plantillas": []}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{GRAPH_API}/{numero['waba_id']}/message_templates",
                        params={"access_token": numero["access_token"], "limit": 100})
    if r.status_code >= 400:
        log.error("No se pudieron listar plantillas (%s): %s", numero["waba_id"], r.text[:300])
        raise HTTPException(status_code=502, detail="Meta no pudo listar las plantillas de este número.")
    plantillas = []
    for t in r.json().get("data", []):
        cuerpo = next((c.get("text") for c in t.get("components", []) if c.get("type") == "BODY"), "")
        plantillas.append({
            "nombre": t.get("name"), "idioma": t.get("language"), "estatus": t.get("status"),
            "categoria": t.get("category"), "cuerpo": cuerpo,
        })
    return {"plantillas": plantillas}


async def wa2_plantilla_crear_core(req, request, *, _require_user, _ids_visibles, sb_get,
                                   _in_filter, HTTPException, re, httpx, GRAPH_API, log):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    numero_rows = await sb_get("wa2_numeros", {"id": f"eq.{req.numero_id}", "user_id": _in_filter(ids),
                                                "select": "*", "limit": "1"})
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]
    if not numero.get("waba_id") or not numero.get("access_token"):
        raise HTTPException(status_code=400, detail="Este número todavía no está conectado del todo con Meta.")

    nombre = re.sub(r"[^a-z0-9_]", "_", req.nombre.strip().lower())
    componentes = [{"type": "BODY", "text": req.cuerpo}]
    if req.variables_ejemplo:
        componentes[0]["example"] = {"body_text": [req.variables_ejemplo]}
    if req.footer:
        componentes.append({"type": "FOOTER", "text": req.footer})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['waba_id']}/message_templates",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"name": nombre, "language": req.idioma,
                               "category": req.categoria, "components": componentes})
    if r.status_code >= 400:
        log.error("No se pudo crear la plantilla (%s): %s", numero["waba_id"], r.text[:300])
        try:
            err = r.json().get("error", {})
            msg = err.get("error_user_msg") or err.get("message")
        except Exception:
            msg = None
        raise HTTPException(status_code=502,
            detail=msg or "Meta rechazó la plantilla. Revisa que el texto no tenga datos personales sueltos "
                          "(usa {{1}}, {{2}}… para lo que cambie en cada envío) y que no repita mucho espacio o salto de línea.")
    return {"ok": True, "nombre": nombre}


async def wa2_enviar_plantilla_core(req, request, *, _require_user, _ids_visibles, sb_get,
                                    _in_filter, HTTPException, httpx, GRAPH_API, log,
                                    _guardar_mensaje):
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

    componentes = []
    if req.variables:
        componentes.append({"type": "body", "parameters": [{"type": "text", "text": v} for v in req.variables]})

    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": contacto.get("wa_id"), "type": "template",
                               "template": {"name": req.nombre, "language": {"code": req.idioma},
                                           "components": componentes}})
    if r.status_code >= 400:
        log.error("Envío de plantilla falló (%s): %s", numero["phone_number_id"], r.text[:300])
        try:
            msg = r.json().get("error", {}).get("message")
        except Exception:
            msg = None
        raise HTTPException(status_code=502, detail=msg or "Meta no pudo mandar la plantilla. Revisa que esté aprobada.")

    d = r.json()
    msgs = d.get("messages") or []
    wamid = msgs[0].get("id") if msgs else None
    resumen = f"[Plantilla: {req.nombre}]" + (" " + " · ".join(req.variables) if req.variables else "")
    await _guardar_mensaje(conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", resumen)
    return {"ok": True}
