from __future__ import annotations


async def wa2_automatizaciones_list_core(request, *, _require_user, _ids_visibles, sb_get, _in_filter):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_automatizaciones", {"user_id": _in_filter(ids), "select": "*",
                                                 "order": "created_at.desc", "limit": "100"})
    return {"automatizaciones": rows}


async def wa2_automatizacion_crear_core(req, request, *, _require_user, _limpiar_automatizacion,
                                        _ids_visibles, sb_get, _in_filter, HTTPException,
                                        _now, sb_post):
    user_id = await _require_user(request)
    fila = _limpiar_automatizacion(req)
    if fila["numero_id"]:
        ids = await _ids_visibles(user_id)
        n = await sb_get("wa2_numeros", {"id": f"eq.{fila['numero_id']}",
                                         "user_id": _in_filter(ids), "select": "id", "limit": "1"})
        if not n:
            raise HTTPException(status_code=404, detail="Número no encontrado")
    fila.update({"user_id": user_id, "veces_usada": 0,
                 "created_at": _now(), "updated_at": _now()})
    creado = await sb_post("wa2_automatizaciones", fila)
    if not creado:
        raise HTTPException(status_code=500,
                            detail="No se pudo guardar. ¿Ya corriste la migración de automatizaciones?")
    return {"ok": True}


async def wa2_automatizacion_patch_core(auto_id, request, *, _require_user, _ids_visibles,
                                        _in_filter, sb_get, HTTPException, AutomatizacionReq,
                                        _limpiar_automatizacion, _now, sb_patch):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {}
    if "activa" in body:
        permitido["activa"] = bool(body["activa"])
    if any(k in body for k in ("nombre", "disparador", "palabras", "acciones", "numero_id")):
        actual_rows = await sb_get("wa2_automatizaciones",
                                   {"id": f"eq.{auto_id}", "user_id": _in_filter(ids),
                                    "select": "*", "limit": "1"})
        if not actual_rows:
            raise HTTPException(status_code=404, detail="Automatización no encontrada")
        actual = actual_rows[0]
        req = AutomatizacionReq(
            nombre=body.get("nombre", actual.get("nombre") or ""),
            numero_id=body.get("numero_id", actual.get("numero_id")),
            disparador=body.get("disparador", actual.get("disparador") or "palabra"),
            palabras=body.get("palabras", actual.get("palabras") or []),
            acciones=body.get("acciones", actual.get("acciones") or []),
            activa=bool(body.get("activa", actual.get("activa", True))),
        )
        permitido.update(_limpiar_automatizacion(req))
    if not permitido:
        return {"ok": True}
    permitido["updated_at"] = _now()
    await sb_patch("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)}, permitido)
    return {"ok": True}
