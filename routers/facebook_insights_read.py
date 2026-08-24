"""Read-only Facebook Ads insights with validated levels and breakdowns."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_paginate
from core.facebook_insights import (
    FB_BREAKDOWNS,
    FB_DATE_PRESETS,
    FB_INSIGHTS_FIELDS,
    normalize_facebook_insights,
)


router = APIRouter()


@router.get("/facebook/insights")
async def facebook_insights(request: Request):
    """Insights a cualquier nivel, con desgloses."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    qp = request.query_params
    object_id = (qp.get("object_id") or "").strip()
    if not object_id:
        raise HTTPException(status_code=400, detail="object_id requerido")

    level = (qp.get("level") or "campaign").strip().lower()
    if level not in ("account", "campaign", "adset", "ad"):
        raise HTTPException(status_code=400, detail="level debe ser account, campaign, adset o ad")

    date_preset = (qp.get("date_preset") or "last_7d").strip()
    if date_preset not in FB_DATE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Periodo no válido. Usa uno de: {', '.join(sorted(FB_DATE_PRESETS))}",
        )

    breakdowns_raw = [b.strip() for b in (qp.get("breakdowns") or "").split(",") if b.strip()]
    invalidos = [b for b in breakdowns_raw if b not in FB_BREAKDOWNS]
    if invalidos:
        raise HTTPException(
            status_code=400,
            detail=f"Desglose no soportado: {', '.join(invalidos)}. "
            f"Disponibles: {', '.join(sorted(FB_BREAKDOWNS))}",
        )

    params = {
        "level": level,
        "fields": FB_INSIGHTS_FIELDS + ",campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name",
        "date_preset": date_preset,
        "limit": "200",
    }
    if breakdowns_raw:
        params["breakdowns"] = ",".join(breakdowns_raw)

    async with httpx.AsyncClient(timeout=60) as client:
        filas = await _fb_paginate(
            client,
            f"{object_id}/insights",
            token=user_token,
            params=params,
            max_items=1000,
            prefix="Error obteniendo métricas",
        )

    salida = []
    for fila in filas:
        registro = normalize_facebook_insights(fila)
        for k in ("campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name"):
            if fila.get(k):
                registro[k] = fila[k]
        for b in breakdowns_raw:
            if b in fila:
                registro[b] = fila[b]
        salida.append(registro)

    return {
        "rows": salida,
        "level": level,
        "date_preset": date_preset,
        "breakdowns": breakdowns_raw,
        "total": len(salida),
    }
