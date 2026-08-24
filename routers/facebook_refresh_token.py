"""Refresh the organization's Facebook long-lived user token."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta
from core.facebook_graph import _fb_friendly_error, _fb_request
from core.facebook_token_lifecycle import (
    FB_TOKEN_DEFAULT_LIFETIME_SECONDS,
    debug_facebook_token,
)
from routers.organizaciones import exigir_gestion_integraciones

router = APIRouter()


@router.post("/facebook/refresh-token")
async def facebook_refresh_token(request: Request):
    """Renueva el token de larga duración sin volver a pasar por el OAuth."""
    user_id = await exigir_gestion_integraciones(request)
    fb_app_id = settings.legacy_main_fb_app_id
    fb_app_secret = settings.legacy_main_fb_app_secret
    if not fb_app_id or not fb_app_secret:
        raise HTTPException(status_code=500, detail="FB_APP_ID o FB_APP_SECRET no configurados.")

    row = await get_facebook_meta_row(user_id)
    meta = row.get("meta") or {}
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="No hay conexión de Facebook que renovar.")

    async with httpx.AsyncClient(timeout=15) as client:
        response = await _fb_request(
            client,
            "GET",
            "oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": fb_app_id,
                "client_secret": fb_app_secret,
                "fb_exchange_token": user_token,
            },
        )
        if response is None or response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=_fb_friendly_error(
                    response.text if response is not None else "",
                    "No se pudo renovar la conexión con Facebook. Reconéctala desde tu perfil",
                ),
            )

        data = response.json() or {}
        new_token = data.get("access_token", "")
        if not new_token:
            raise HTTPException(
                status_code=502,
                detail="Facebook no devolvió un token nuevo. Reconecta desde tu perfil.",
            )
        try:
            expires_in = int(data.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        info = await debug_facebook_token(client, new_token)

    lifetime = expires_in or FB_TOKEN_DEFAULT_LIFETIME_SECONDS
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=lifetime)).isoformat()
    await patch_facebook_meta(
        user_id,
        {
            "user_token": new_token,
            "token_expires_at": expires_at,
            "scopes": info.get("scopes") or meta.get("scopes") or [],
            "token_refreshed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "ok": True,
        "token_expires_at": expires_at,
        "dias_restantes": int(lifetime / 86400),
    }
