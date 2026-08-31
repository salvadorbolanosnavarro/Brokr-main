"""Read-only Facebook campaign review status and rejection details."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_get_json, _fb_paginate


router = APIRouter()

_FB_EFFECTIVE_STATUSES = {
    "ACTIVE": ("ok", "Entregando"),
    "PAUSED": ("neutro", "Pausado por ti"),
    "DELETED": ("neutro", "Eliminado"),
    "ARCHIVED": ("neutro", "Archivado"),
    "PENDING_REVIEW": ("aviso", "En revisión por Meta (suele tardar menos de 24 h)"),
    "IN_PROCESS": ("aviso", "Meta lo está procesando"),
    "PREAPPROVED": ("aviso", "Preaprobado, aún no entrega"),
    "DISAPPROVED": ("error", "Rechazado por Meta"),
    "WITH_ISSUES": ("error", "Con observaciones de Meta"),
    "PENDING_BILLING_INFO": ("error", "Falta método de pago en la cuenta publicitaria"),
    "CAMPAIGN_PAUSED": ("neutro", "La campaña padre está pausada"),
    "ADSET_PAUSED": ("neutro", "El conjunto padre está pausado"),
}


@router.get("/facebook/campaign/review")
async def facebook_campaign_review(request: Request):
    """Estado de revisión real de una campaña, anuncio por anuncio."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    campaign_id = (request.query_params.get("campaign_id") or "").strip()
    if not campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id requerido")
    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    async with httpx.AsyncClient(timeout=30) as client:
        campana = await _fb_get_json(
            client,
            campaign_id,
            token=user_token,
            params={"fields": "id,name,status,effective_status"},
            prefix="Error leyendo la campaña",
        )
        anuncios = await _fb_paginate(
            client,
            f"{campaign_id}/ads",
            token=user_token,
            params={
                "fields": "id,name,status,effective_status,"
                "ad_review_feedback,issues_info,adset_id",
                "limit": "50",
            },
            prefix="Error leyendo los anuncios",
        )

    def _motivos(ad: dict) -> list:
        salida = []
        feedback = ad.get("ad_review_feedback") or {}
        for bloque in feedback.values():
            if isinstance(bloque, dict):
                salida.extend(str(v) for v in bloque.values() if v)
            elif bloque:
                salida.append(str(bloque))
        for issue in (ad.get("issues_info") or []):
            if not isinstance(issue, dict):
                continue
            texto = issue.get("error_summary") or issue.get("error_message") or ""
            if texto:
                salida.append(str(texto))
        return list(dict.fromkeys([s for s in salida if s.strip()]))

    detalle = []
    for ad in anuncios:
        eff = ad.get("effective_status", "")
        severidad, etiqueta = _FB_EFFECTIVE_STATUSES.get(eff, ("neutro", eff or "Desconocido"))
        detalle.append(
            {
                "ad_id": ad.get("id", ""),
                "adset_id": ad.get("adset_id", ""),
                "name": ad.get("name", ""),
                "status": ad.get("status", ""),
                "effective_status": eff,
                "severidad": severidad,
                "etiqueta": etiqueta,
                "motivos": _motivos(ad),
                "apelable": eff in ("DISAPPROVED", "WITH_ISSUES"),
            }
        )

    eff_camp = campana.get("effective_status", "")
    sev_camp, etq_camp = _FB_EFFECTIVE_STATUSES.get(
        eff_camp,
        ("neutro", eff_camp or "Desconocido"),
    )
    rechazados = [d for d in detalle if d["severidad"] == "error"]

    return {
        "campaign_id": campaign_id,
        "name": campana.get("name", ""),
        "status": campana.get("status", ""),
        "effective_status": eff_camp,
        "severidad": "error" if rechazados else sev_camp,
        "etiqueta": etq_camp,
        "ads": detalle,
        "con_problemas": len(rechazados),
        "url_revision": f"https://www.facebook.com/adsmanager/manage/ads?selected_campaign_ids={campaign_id}",
    }
