"""Editable WhatsApp contact qualification/settings."""
from __future__ import annotations

from fastapi import APIRouter, Request

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_patch
from routers.whatsapp_time import now_iso as _now
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter()


@router.patch("/contactos/{contacto_id}")
async def wa2_contacto_patch(contacto_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    body = await request.json()
    permitido = {k: v for k, v in body.items()
                if k in ("nombre", "presupuesto", "forma_pago", "busca", "temperatura", "score", "etapa", "resumen", "opt_out")}
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
