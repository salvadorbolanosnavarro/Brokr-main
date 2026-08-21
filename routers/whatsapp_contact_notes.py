"""Manual notes for WhatsApp contacts, mirrored into the CRM."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_crm_bridge import sincronizar_contacto_crm as _sincronizar_contacto_crm
from routers.whatsapp_data import sb_get, sb_patch
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotaReq(BaseModel):
    texto: str


@router.post("/contactos/{contacto_id}/notas")
async def wa2_agregar_nota(contacto_id: str, req: NotaReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_contactos",
        {"id": f"eq.{contacto_id}", "user_id": _in_filter(ids), "select": "notas,contacto_crm_id", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    notas = (rows[0].get("notas") or []) + [{"texto": req.texto, "autor": "agente", "fecha": _now()}]
    await sb_patch(
        "wa2_contactos",
        {"id": f"eq.{contacto_id}"},
        {"notas": notas, "updated_at": _now()},
    )
    await _sincronizar_contacto_crm(user_id, rows[0], {"nota": req.texto})
    return {"ok": True, "notas": notas}
