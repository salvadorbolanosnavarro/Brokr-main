"""Send approved WhatsApp templates into an existing inbox conversation."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_cloud_api import send_template
from routers.whatsapp_data import sb_get
from routers.whatsapp_messages import guardar_mensaje as _guardar_mensaje
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])


class PlantillaEnviarReq(BaseModel):
    conversacion_id: str
    nombre: str
    idioma: str
    variables: list[str] = []


@router.post("/mensajes/plantilla")
async def wa2_enviar_plantilla(req: PlantillaEnviarReq, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    conv_rows = await sb_get(
        "wa2_conversaciones",
        {"id": f"eq.{req.conversacion_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not conv_rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = conv_rows[0]
    contacto_rows = await sb_get(
        "wa2_contactos", {"id": f"eq.{conv['contacto_id']}", "select": "*", "limit": "1"}
    )
    contacto = contacto_rows[0] if contacto_rows else {}
    numero_rows = await sb_get(
        "wa2_numeros", {"id": f"eq.{conv['numero_id']}", "select": "*", "limit": "1"}
    )
    if not numero_rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    numero = numero_rows[0]

    wamid, error = await send_template(
        numero,
        contacto.get("wa_id"),
        req.nombre,
        req.idioma,
        req.variables,
    )
    if error:
        raise HTTPException(
            status_code=502,
            detail=error.get("message") or "Meta no pudo mandar la plantilla. Revisa que esté aprobada.",
        )

    resumen = f"[Plantilla: {req.nombre}]" + (
        " " + " · ".join(req.variables) if req.variables else ""
    )
    await _guardar_mensaje(
        conv["user_id"], conv["contacto_id"], conv["id"], wamid, "out", "agente", resumen
    )
    return {"ok": True}
