"""Read-only WhatsApp 2.0 inbox endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get
from routers.whatsapp_utils import in_filter as _in_filter


log = logging.getLogger("broquer.whatsapp2")
router = APIRouter()


@router.get("/conversaciones")
async def wa2_conversaciones_list(request: Request, numero_id: str | None = None):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    params = {"user_id": _in_filter(ids), "select": "*,wa2_contactos(*)",
              "order": "last_message_at.desc", "limit": "200"}
    if numero_id and numero_id != "todos":
        params["numero_id"] = f"eq.{numero_id}"
    rows = await sb_get("wa2_conversaciones", params)

    if rows:
        try:
            recientes = await sb_get("wa2_mensajes", {
                "user_id": _in_filter(ids),
                "select": "conversacion_id,body,direction,sender,created_at",
                "order": "created_at.desc", "limit": "1000",
            })
            vistos: dict = {}
            for m in recientes:
                cid = m.get("conversacion_id")
                if cid and cid not in vistos:
                    vistos[cid] = m
            for c in rows:
                ult = vistos.get(c.get("id"))
                if ult:
                    c["preview_texto"] = (ult.get("body") or "")[:120]
                    c["preview_direction"] = ult.get("direction")
                    c["preview_sender"] = ult.get("sender")
        except Exception:
            log.warning("No se pudo calcular la vista previa de las conversaciones")

    return {"conversaciones": rows}


@router.get("/mensajes")
async def wa2_mensajes_list(request: Request, conversacion_id: str,
                            limit: int = 30, before: str | None = None, after: str | None = None):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    limit = max(1, min(int(limit or 30), 100))

    base = {"conversacion_id": f"eq.{conversacion_id}", "user_id": _in_filter(ids), "select": "*"}

    if after:
        rows = await sb_get("wa2_mensajes", {**base, "created_at": f"gt.{after}",
                                             "order": "created_at.asc", "limit": "200"})
        return {"mensajes": rows, "hay_mas_antiguos": False, "incremental": True}

    params = {**base, "order": "created_at.desc", "limit": str(limit + 1)}
    if before:
        params["created_at"] = f"lt.{before}"
    rows = await sb_get("wa2_mensajes", params)

    hay_mas = len(rows) > limit
    if hay_mas:
        rows = rows[:limit]
    rows.reverse()
    return {"mensajes": rows, "hay_mas_antiguos": hay_mas, "incremental": False}
