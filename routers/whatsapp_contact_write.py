from __future__ import annotations


async def wa2_agregar_nota_core(contacto_id: str, req, request, *,
                                _require_user, _ids_visibles, sb_get, _in_filter,
                                HTTPException, _now, sb_patch, _sincronizar_contacto_crm):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_contactos", {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids),
                                          "select": "notas,contacto_crm_id", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    notas = (rows[0].get("notas") or []) + [{"texto": req.texto, "autor": "agente", "fecha": _now()}]
    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_id}"}, {"notas": notas, "updated_at": _now()})
    await _sincronizar_contacto_crm(user_id, rows[0], {"nota": req.texto})
    return {"ok": True, "notas": notas}


async def wa2_contacto_patch_core(contacto_id: str, request, *,
                                  _require_user, _ids_visibles, _in_filter,
                                  _now, sb_patch):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {k: v for k, v in body.items()
                if k in ("nombre", "presupuesto", "forma_pago", "busca", "temperatura", "score", "etapa", "resumen", "opt_out")}
    # Etiquetas: solo lista de textos cortos, sin repetidos y con tope, para
    # que un cliente no pueda meter basura enorme por el API.
    if "etiquetas" in body and isinstance(body["etiquetas"], list):
        limpias = []
        for e in body["etiquetas"]:
            t = str(e).strip()[:40]
            if t and t not in limpias:
                limpias.append(t)
        permitido["etiquetas"] = limpias[:20]
    if not permitido:
        return {"ok": True}
    permitido["updated_at"] = _now()
    await sb_patch("wa2_contactos", {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}
