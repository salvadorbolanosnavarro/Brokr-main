"""Server-side persistence helpers for the Facebook integration.

This module deliberately exposes decrypted credentials only to backend callers.
Browser-facing routers must return a redacted projection instead of passing
these rows through directly.
"""
from __future__ import annotations

import json

import httpx

from core.config import settings
from core.database import get_rows
from core.facebook_secrets import decrypt_facebook_secret


async def get_facebook_meta_row(user_id: str) -> dict:
    """Return the user's Facebook integration row with server-side tokens decoded.

    Preserve the legacy fail-soft contract: missing privileged configuration,
    a missing row, malformed metadata, or a Supabase HTTP rejection all read as
    an empty result. Transport failures still propagate to the caller.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        return {}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        return {}
    if not rows:
        return {}

    row = rows[0]
    meta_raw = row.get("meta", "{}")
    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}

    if meta.get("user_token"):
        meta["user_token"] = decrypt_facebook_secret(meta["user_token"])
    return {
        "page_token": decrypt_facebook_secret(row.get("api_key", "")),
        "meta": meta,
    }
