from __future__ import annotations


async def wa2_conversacion_patch_core(conversacion_id: str, req, request, *,
                                      _require_user, _ids_visibles, sb_get,
                                      _in_filter, HTTPException, sb_patch):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "contacto_id", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    modo = req.ia_modo
    if modo is None and req.ai_enabled is not None:
        # Clientes viejos (la app de iOS hasta que se recompile) siguen
        # mandando el booleano: se traduce al modo equivalente.
        modo = "on" if req.ai_enabled else "off"
    if modo is not None:
        if modo not in ("auto", "on", "off"):
            raise HTTPException(status_code=400, detail="ia_modo debe ser auto, on u off")
        # Cualquier cambio explícito del agente borra la pausa temporal:
        # si la acaba de encender, es porque QUIERE que conteste ya.
        cambios = {"ia_modo": modo, "ai_enabled": modo != "off", "ia_pausada_hasta": None}
        guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios)
        if not guardado:
            # Migración pendiente: degradar al booleano clásico.
            await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                           {"ai_enabled": modo != "off"})
    if req.etapa is not None:
        await sb_patch("wa2_contactos", {"id": f"eq.{conv_rows[0]['contacto_id']}"}, {"etapa": req.etapa})
    return {"ok": True}
