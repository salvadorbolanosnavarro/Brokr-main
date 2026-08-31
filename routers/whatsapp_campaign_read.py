"""Read-only WhatsApp campaign and label queries."""
from __future__ import annotations


async def wa2_etiquetas_list_core(request, *, _require_user, _ids_visibles, sb_get, _in_filter):
    """Todas las etiquetas distintas que el usuario ha puesto a sus contactos
    de WhatsApp — alimenta el selector de audiencia de campañas."""
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_contactos", {"user_id": _in_filter(ids),
                                          "select": "etiquetas", "limit": "5000"})
    etiquetas = sorted({str(e).strip() for c in rows
                        for e in (c.get("etiquetas") or []) if str(e).strip()})
    return {"etiquetas": etiquetas}


async def wa2_campanas_list_core(request, *, _require_user, _ids_visibles, sb_get, _in_filter):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_campanas", {"user_id": _in_filter(ids), "select": "*",
                                         "order": "created_at.desc", "limit": "30"})
    return {"campanas": rows}


async def wa2_campana_detalle_core(campana_id: str, request, *, _require_user,
                                   _ids_visibles, sb_get, _in_filter, HTTPException):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_campanas", {"id": f"eq.{campana_id}",
                                         "user_id": _in_filter(ids),
                                         "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    fallidos = await sb_get("wa2_campana_envios", {"campana_id": f"eq.{campana_id}",
                                                   "estado": "eq.fallido",
                                                   "select": "nombre,wa_id,error",
                                                   "limit": "200"})
    return {"campana": rows[0], "fallidos": fallidos}
