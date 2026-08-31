"""Read-only status for automatic Facebook Lead Ads capture."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.facebook_connection_store import get_facebook_meta_row
from core.facebook_graph import _fb_paginate
from core.facebook_leadgen_config import FB_VERIFY_TOKEN, FB_WEBHOOK_SECRET


router = APIRouter()


@router.get("/facebook/leadgen/status")
async def facebook_leadgen_status(request: Request):
    """Dice si la página está capturando prospectos automáticamente."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    fila = await get_facebook_meta_row(user_id)
    meta = fila.get("meta") or {}
    page_id = meta.get("page_id", "")
    page_token = fila.get("page_token", "")
    if not page_id or not page_token:
        return {
            "configurado": False,
            "suscrito": False,
            "motivo": "No hay página de Facebook conectada.",
        }
    if not FB_VERIFY_TOKEN or not FB_WEBHOOK_SECRET:
        return {
            "configurado": False,
            "suscrito": False,
            "motivo": "El servidor no tiene FB_VERIFY_TOKEN o FB_APP_SECRET configurados.",
        }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            apps = await _fb_paginate(
                client,
                f"{page_id}/subscribed_apps",
                token=page_token,
                params={"fields": "id,name,subscribed_fields"},
                max_paginas=1,
                prefix="Error consultando la suscripción",
            )
    except HTTPException as e:
        return {"configurado": True, "suscrito": False, "motivo": str(e.detail)}

    suscrito = any("leadgen" in (a.get("subscribed_fields") or []) for a in apps)
    return {
        "configurado": True,
        "suscrito": suscrito,
        "page_id": page_id,
        "motivo": "" if suscrito else "La página no está suscrita a los avisos de prospectos.",
        "webhook_url": f"{settings.legacy_main_frontend_url.rstrip('/')}/facebook/leadgen/webhook",
    }
