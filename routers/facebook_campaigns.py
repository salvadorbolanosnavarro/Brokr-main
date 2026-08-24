"""Read-only Facebook campaigns listing with normalized Meta insights."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_paginate
from core.facebook_insights import (
    FB_DATE_PRESETS,
    FB_INSIGHTS_FIELDS,
    normalize_facebook_insights,
)


router = APIRouter()
_fb_log = logging.getLogger("broquer.facebook")


@router.get("/facebook/campaigns")
async def facebook_campaigns_list(request: Request):
    """Lista las campañas con sus métricas reales."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    account_id_raw = request.query_params.get("account_id", "")
    if not account_id_raw:
        raise HTTPException(status_code=400, detail="account_id requerido")
    account_id = account_id_raw if account_id_raw.startswith("act_") else f"act_{account_id_raw}"

    date_preset = (request.query_params.get("date_preset") or "last_7d").strip()
    if date_preset not in FB_DATE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Periodo no válido. Usa uno de: {', '.join(sorted(FB_DATE_PRESETS))}",
        )

    async with httpx.AsyncClient(timeout=40) as client:
        campaigns = await _fb_paginate(
            client,
            f"{account_id}/campaigns",
            token=user_token,
            params={
                "fields": "id,name,status,effective_status,objective,created_time,"
                "daily_budget,lifetime_budget,stop_time",
                "limit": "50",
            },
            max_items=200,
            prefix="Error obteniendo campañas",
        )

        insights_por_campana: dict = {}
        try:
            filas = await _fb_paginate(
                client,
                f"{account_id}/insights",
                token=user_token,
                params={
                    "level": "campaign",
                    "fields": FB_INSIGHTS_FIELDS + ",campaign_id",
                    "date_preset": date_preset,
                    "limit": "200",
                },
                max_items=500,
                prefix="Error obteniendo métricas",
            )
            for fila in filas:
                cid = fila.get("campaign_id")
                if cid:
                    insights_por_campana[cid] = normalize_facebook_insights(fila)
        except HTTPException as e:
            _fb_log.warning("Insights no disponibles para %s: %s", account_id, e.detail)

    vacio = normalize_facebook_insights({})
    results = []
    for camp in campaigns:
        cid = camp.get("id", "")
        results.append(
            {
                "id": cid,
                "name": camp.get("name", ""),
                "status": camp.get("status", ""),
                "effective_status": camp.get("effective_status", ""),
                "objective": camp.get("objective", ""),
                "created_time": camp.get("created_time", ""),
                "stop_time": camp.get("stop_time", ""),
                "daily_budget": camp.get("daily_budget", ""),
                **insights_por_campana.get(cid, vacio),
            }
        )
    return {
        "campaigns": results,
        "date_preset": date_preset,
        "con_metricas": bool(insights_por_campana),
    }
