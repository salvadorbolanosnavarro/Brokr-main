"""Read-only WhatsApp campaign views and audience preview."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_data import sb_get
from routers.whatsapp_identity import es_asesor as _es_asesor
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])
WA2_CAMPANA_TOPE = settings.wa2_campaign_limit


class CampanaAudienciaReq(BaseModel):
    numero_id: str
    etiqueta: str | None = None


async def _audiencia_campana(numero: dict, etiqueta: str | None) -> list:
    params = {
        "numero_id": f"eq.{numero['id']}",
        "user_id": f"eq.{numero['user_id']}",
        "select": "id,wa_id,nombre,opt_out,etiquetas",
        "limit": "5000",
    }
    if etiqueta:
        params["etiquetas"] = "cs." + json.dumps([etiqueta])
    rows = await sb_get("wa2_contactos", params)
    audiencia = []
    for c in rows:
        if not c.get("wa_id") or c.get("opt_out"):
            continue
        if _es_asesor(numero, c["wa_id"]):
            continue
        audiencia.append(c)
    return audiencia


async def _numero_visible(request: Request, numero_id: str) -> tuple[str, dict]:
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_numeros",
        {"id": f"eq.{numero_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return user_id, rows[0]


@router.get("/etiquetas")
async def wa2_etiquetas_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_contactos", {"user_id": _in_filter(ids), "select": "etiquetas", "limit": "5000"}
    )
    etiquetas = sorted(
        {str(e).strip() for c in rows for e in (c.get("etiquetas") or []) if str(e).strip()}
    )
    return {"etiquetas": etiquetas}


@router.post("/campanas/audiencia")
async def wa2_campana_audiencia(req: CampanaAudienciaReq, request: Request):
    _, numero = await _numero_visible(request, req.numero_id)
    audiencia = await _audiencia_campana(numero, (req.etiqueta or "").strip() or None)
    return {"total": len(audiencia), "tope": WA2_CAMPANA_TOPE}


@router.get("/campanas")
async def wa2_campanas_list(request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_campanas",
        {"user_id": _in_filter(ids), "select": "*", "order": "created_at.desc", "limit": "30"},
    )
    return {"campanas": rows}


@router.get("/campanas/{campana_id}")
async def wa2_campana_detalle(campana_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get(
        "wa2_campanas",
        {"id": f"eq.{campana_id}", "user_id": _in_filter(ids), "select": "*", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    fallidos = await sb_get(
        "wa2_campana_envios",
        {
            "campana_id": f"eq.{campana_id}",
            "estado": "eq.fallido",
            "select": "nombre,wa_id,error",
            "limit": "200",
        },
    )
    return {"campana": rows[0], "fallidos": fallidos}
