"""Shared Meta token lifetime and debug-token inspection."""
from __future__ import annotations

import httpx

from core.config import settings
from core.facebook_graph import _fb_request

FB_TOKEN_DEFAULT_LIFETIME_SECONDS = 60 * 24 * 3600


async def debug_facebook_token(client: httpx.AsyncClient, token: str) -> dict:
    """Return Meta /debug_token data, preserving the historical fail-soft contract."""
    app_id = settings.legacy_main_fb_app_id
    app_secret = settings.legacy_main_fb_app_secret
    if not token or not app_id or not app_secret:
        return {}
    try:
        response = await _fb_request(
            client,
            "GET",
            "debug_token",
            params={
                "input_token": token,
                "access_token": f"{app_id}|{app_secret}",
            },
            reintentos=2,
        )
        if response is None or response.status_code != 200:
            return {}
        return (response.json() or {}).get("data") or {}
    except Exception:
        return {}
