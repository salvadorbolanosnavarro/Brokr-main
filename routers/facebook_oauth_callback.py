"""Facebook OAuth callback and long-lived token exchange."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from core.config import settings
from core.facebook_graph import _fb_exigir_ok, _fb_friendly_error, _fb_paginate, _fb_request
from core.facebook_token_lifecycle import (
    FB_TOKEN_DEFAULT_LIFETIME_SECONDS,
    debug_facebook_token,
)
from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES

router = APIRouter()
log = logging.getLogger("broquer.facebook")


@router.get("/facebook/callback")
async def facebook_callback(
    code: str = Query(...),
    state: str = Query(None),
    redirect_uri: str = Query(None),
):
    """Intercambia el code OAuth por un token de usuario de larga duración."""
    fb_app_id = settings.legacy_main_fb_app_id
    fb_app_secret = settings.legacy_main_fb_app_secret
    frontend_url = settings.legacy_main_frontend_url
    if not fb_app_id or not fb_app_secret:
        raise HTTPException(
            status_code=500,
            detail="FB_APP_ID o FB_APP_SECRET no configurados en el servidor.",
        )

    redirect_uri = redirect_uri or (frontend_url + "/facebook/callback")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await _fb_request(
            client,
            "GET",
            "oauth/access_token",
            params={
                "client_id": fb_app_id,
                "client_secret": fb_app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        short_token = _fb_exigir_ok(
            response,
            "No se pudo completar la conexión con Facebook",
            status_code=400,
        ).get("access_token", "")
        if not short_token:
            raise HTTPException(
                status_code=502,
                detail="Facebook no devolvió un token de acceso. Intenta conectar de nuevo.",
            )

        long_response = await _fb_request(
            client,
            "GET",
            "oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": fb_app_id,
                "client_secret": fb_app_secret,
                "fb_exchange_token": short_token,
            },
        )
        if long_response is None or long_response.status_code != 200:
            log.error(
                "fb_exchange_token falló: %s",
                (long_response.text if long_response is not None else "sin respuesta")[:400],
            )
            raise HTTPException(
                status_code=502,
                detail=_fb_friendly_error(
                    long_response.text if long_response is not None else "",
                    "Facebook no entregó un token de larga duración, así que no se guardó "
                    "la conexión (con el token corto los anuncios dejarían de funcionar en "
                    "una hora). Intenta conectar de nuevo",
                ),
            )

        token_data = long_response.json() or {}
        long_token = token_data.get("access_token", "")
        if not long_token:
            raise HTTPException(
                status_code=502,
                detail="Facebook no devolvió el token de larga duración. Intenta conectar de nuevo.",
            )

        try:
            expires_in = int(token_data.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        token_expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=expires_in or FB_TOKEN_DEFAULT_LIFETIME_SECONDS)
        ).isoformat()

        token_info = await debug_facebook_token(client, long_token)
        missing_scopes = [
            scope
            for scope in FACEBOOK_REQUIRED_SCOPES
            if scope not in (token_info.get("scopes") or [])
        ]
        pages = await _fb_paginate(
            client,
            "me/accounts",
            token=long_token,
            params={"fields": "id,name,access_token", "limit": "100"},
            prefix="Error leyendo tus páginas",
        )

    if not pages:
        raise HTTPException(
            status_code=400,
            detail="No se encontraron páginas administradas en esta cuenta de Facebook. "
            "Crea o pide acceso a una página antes de conectar.",
        )

    page = pages[0]
    return {
        "ok": True,
        "page_id": page.get("id", ""),
        "page_name": page.get("name", ""),
        "page_token": page.get("access_token", ""),
        "user_token": long_token,
        "token_expires_at": token_expires_at,
        "token_expires_in": expires_in,
        "scopes": token_info.get("scopes") or [],
        "scopes_faltantes": missing_scopes,
        "pages": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "access_token": item.get("access_token"),
            }
            for item in pages
        ],
    }
