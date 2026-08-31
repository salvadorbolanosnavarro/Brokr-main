"""Manual read/unread state for WhatsApp inbox conversations."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_cloud_api import marcar_leido as _wa_marcar_leido
from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])


class LecturaReq(BaseModel):
    no_leida: bool = False


@router.post("/conversaciones/{conversacion_id}/lectura")
async def wa2_lectura(conversacion_id: str, req: LecturaReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get(
        "wa2_conversaciones",
        {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]

    if req.no_leida:
        await sb_patch(
            "wa2_conversaciones",
            {"id": f"eq.{conversacion_id}"},
            {"no_leida": True, "unread_count": max(1, int(conv.get("unread_count") or 0))},
        )
        return {"ok": True, "no_leida": True}

    await sb_patch(
        "wa2_conversaciones",
        {"id": f"eq.{conversacion_id}"},
        {"no_leida": False, "unread_count": 0},
    )

    wamid = conv.get("last_inbound_wamid")
    if wamid:
        numero_rows = await sb_get(
            "wa2_numeros", {"id": f"eq.{conv.get('numero_id')}", "select": "*", "limit": "1"}
        )
        if numero_rows:
            await _wa_marcar_leido(numero_rows[0], wamid, escribiendo=False)

    return {"ok": True, "no_leida": False}
