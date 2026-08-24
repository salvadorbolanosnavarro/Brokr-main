"""Subscribe a connected Facebook page to Lead Ads notifications."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta
from core.facebook_graph import _fb_exigir_ok, _fb_paginate, _fb_request
from core.facebook_leadgen_config import FB_VERIFY_TOKEN
from routers.organizaciones import exigir_gestion_integraciones


router = APIRouter()


@router.post("/facebook/leadgen/subscribe")
async def facebook_leadgen_subscribe(request: Request):
    """Suscribe la página del agente a los avisos de Lead Ads."""
    user_id = await exigir_gestion_integraciones(request)
    if not FB_VERIFY_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar FB_VERIFY_TOKEN en el servidor. Sin él, Meta no "
            "puede verificar el webhook y los leads no llegarían.",
        )
    fila = await get_facebook_meta_row(user_id)
    meta = fila.get("meta") or {}
    page_id = meta.get("page_id", "")
    page_token = fila.get("page_token", "")
    if not page_id or not page_token:
        raise HTTPException(status_code=400, detail="Conecta tu página de Facebook primero.")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await _fb_request(
            client,
            "POST",
            f"{page_id}/subscribed_apps",
            token=page_token,
            json_body={"subscribed_fields": ["leadgen"]},
        )
        _fb_exigir_ok(r, "No se pudo activar la captura de prospectos")

        confirmacion = await _fb_paginate(
            client,
            f"{page_id}/subscribed_apps",
            token=page_token,
            params={"fields": "id,name,subscribed_fields"},
            max_paginas=1,
            prefix="No se pudo verificar la suscripción",
        )

    suscrito = any("leadgen" in (a.get("subscribed_fields") or []) for a in confirmacion)
    if not suscrito:
        raise HTTPException(
            status_code=502,
            detail="Meta aceptó la petición pero la página no quedó suscrita a 'leadgen'. "
            "Revisa que tu app tenga el permiso leads_retrieval aprobado.",
        )

    await patch_facebook_meta(
        user_id,
        {
            "leadgen_suscrito": True,
            "leadgen_suscrito_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok": True,
        "page_id": page_id,
        "suscrito": True,
        "nota": "A partir de ahora, los prospectos de tus anuncios con formulario "
        "entran solos a tu lista de prospectos.",
    }
