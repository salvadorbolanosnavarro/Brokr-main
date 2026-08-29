"""Exact non-destructive WhatsApp number administration cores."""


async def wa2_numero_verificar_core(
    numero_id: str, request, *, _require_user, sb_get, HTTPException, httpx,
    GRAPH_API, WA2_WEBHOOK_URL, sb_patch,
):
    """Vuelve a preguntarle a Meta, EN VIVO, si este número de verdad está mandando
    sus mensajes al webhook de WhatsApp 2.0. No confía en lo que se guardó al conectar:
    ese estado pudo cambiar después (ej. alguien reconectó el mismo número en el
    WhatsApp original, lo que le quita el override a este)."""
    user_id = await _require_user(request)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": f"eq.{user_id}",
                                        "select": "waba_id,access_token", "limit": "1"})
    if not rows or not rows[0].get("waba_id") or not rows[0].get("access_token"):
        raise HTTPException(status_code=404, detail="Número no encontrado")
    waba_id, token = rows[0]["waba_id"], rows[0]["access_token"]
    verificado = False
    callback_actual = None
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{GRAPH_API}/{waba_id}/subscribed_apps", params={"access_token": token})
        if r.status_code < 300:
            for app_sub in r.json().get("data", []):
                callback_actual = app_sub.get("override_callback_uri")
                if callback_actual == WA2_WEBHOOK_URL:
                    verificado = True
                    break
        else:
            raise HTTPException(status_code=502, detail=f"Meta respondió con error: {r.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo consultar a Meta: {e}")

    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}"}, {"webhook_verificado": verificado})
    return {"webhook_verificado": verificado, "callback_actual": callback_actual}


async def wa2_numeros_list_core(request, *, _require_user, _ids_visibles, sb_get, _in_filter):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {
        "user_id": _in_filter(ids), "select": "*", "order": "created_at.asc"})
    for r in rows:
        r.pop("access_token", None)
        r["es_mio"] = r.get("user_id") == user_id
    return {"numeros": rows}


async def wa2_numero_patch_core(
    numero_id: str, req, request, *, _require_user, _ids_visibles, _now,
    _normaliza_mx, sb_patch, _in_filter,
):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = {"updated_at": _now()}
    if req.alias is not None:
        body["alias"] = req.alias.strip()
    if req.ia_enabled is not None:
        body["ia_enabled"] = req.ia_enabled
    if req.numero_personal is not None:
        # El número PERSONAL del asesor: desde ahí le escribe a su propio número
        # de Broquer y lo atiende Broq (modo asesor), no la recepcionista.
        # Cadena vacía = quitarlo. Se guarda normalizado (solo dígitos, 52 fijo).
        body["numero_personal"] = _normaliza_mx(req.numero_personal) or None
    await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids)}, body)
    return {"ok": True}
