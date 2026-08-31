"""WhatsApp conversation AI-mode and stage settings."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter()


class ConvPatchReq(BaseModel):
    ai_enabled: bool | None = None
    ia_modo: str | None = None
    etapa: str | None = None


@router.patch("/conversaciones/{conversacion_id}")
async def wa2_conversacion_patch(conversacion_id: str, req: ConvPatchReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get("wa2_conversaciones", {"id": f"eq.{conversacion_id}", "user_id": _in_filter(ids),
                                                    "select": "contacto_id", "limit": "1"})
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    modo = req.ia_modo
    if modo is None and req.ai_enabled is not None:
        modo = "on" if req.ai_enabled else "off"
    if modo is not None:
        if modo not in ("auto", "on", "off"):
            raise HTTPException(status_code=400, detail="ia_modo debe ser auto, on u off")
        cambios = {"ia_modo": modo, "ai_enabled": modo != "off", "ia_pausada_hasta": None}
        guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios)
        if not guardado:
            await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"},
                           {"ai_enabled": modo != "off"})
    if req.etapa is not None:
        await sb_patch("wa2_contactos", {"id": f"eq.{conv_rows[0]['contacto_id']}"}, {"etapa": req.etapa})
    return {"ok": True}
