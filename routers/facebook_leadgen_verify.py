"""Meta Lead Ads webhook verification handshake."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from core.facebook_leadgen_config import FB_VERIFY_TOKEN


router = APIRouter()
_fb_log = logging.getLogger("broquer.facebook")


@router.get("/facebook/leadgen/webhook")
async def facebook_leadgen_verify(request: Request):
    """Handshake de verificación de Meta (hub.challenge)."""
    p = request.query_params
    if not FB_VERIFY_TOKEN:
        _fb_log.error("FB_VERIFY_TOKEN no configurado: el webhook de Lead Ads está cerrado.")
        return Response(content="not configured", status_code=503)
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == FB_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)
