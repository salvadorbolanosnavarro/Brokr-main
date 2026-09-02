"""Read-only WhatsApp inbox endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get
from routers.whatsapp_utils import in_filter as _in_filter


log = logging.getLogger("broquer.whatsapp2")
router = APIRouter()


async def wa2_conversaciones_list_core(request, numero_id: str | None = None, *,
                                       _require_user, _ids_visibles, _in_filter,
                                       sb_get, log):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    params = {"user_id": _in_filter(ids), "select": "*,wa2_contactos(*)",
              "order": "last_message_at.desc", "limit": "200"}
    if numero_id and numero_id != "todos":
        params["numero_id"] = f"eq.{numero_id}"
    rows = await sb_get("wa2_conversaciones", params)

    # Vista previa del último mensaje de cada chat (como WhatsApp). Se resuelve
    # con UNA sola consulta: se traen los mensajes recientes del usuario en
    # orden descendente y se toma el primero que aparece de cada conversación.
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


async def wa2_mensajes_list_core(request, conversacion_id: str,
                                 limit: int = 30, before: str | None = None,
                                 after: str | None = None, *,
                                 _require_user, _ids_visibles, _in_filter, sb_get):
    """Mensajes de una conversación, paginados como WhatsApp.

    · Sin parámetros: devuelve los ÚLTIMOS `limit` mensajes (los más recientes),
      ya ordenados del más viejo al más nuevo para pintarlos de corrido.
    · `before=<created_at>`: devuelve la página ANTERIOR (mensajes más viejos),
      que es lo que se pide al hacer scroll hacia arriba.
    · `after=<created_at>`: solo lo que llegó después de esa marca — se usa en el
      refresco automático para no volver a bajar toda la conversación.
    """
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

    # Bajar los mensajes ya NO marca la conversación como leída. Leer es un
    # acto del agente, no un efecto secundario de que el navegador refresque:
    # de eso se encarga POST /conversaciones/{id}/lectura.
    return {"mensajes": rows, "hay_mas_antiguos": hay_mas, "incremental": False}


@router.get("/conversaciones")
async def wa2_conversaciones_list(request: Request, numero_id: str | None = None):
    return await wa2_conversaciones_list_core(
        request, numero_id,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        _in_filter=_in_filter, sb_get=sb_get, log=log,
    )


@router.get("/mensajes")
async def wa2_mensajes_list(request: Request, conversacion_id: str,
                            limit: int = 30, before: str | None = None, after: str | None = None):
    return await wa2_mensajes_list_core(
        request, conversacion_id, limit, before, after,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        _in_filter=_in_filter, sb_get=sb_get,
    )
