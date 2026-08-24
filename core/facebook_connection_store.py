"""Server-side persistence helpers for the Facebook integration.

This module deliberately exposes decrypted credentials only to backend callers.
Browser-facing routers must return a redacted projection instead of passing
these rows through directly.
"""
from __future__ import annotations

from datetime import datetime
import json

import httpx

from core.config import settings
from core.database import get_rows, post_rows
from core.facebook_secrets import decrypt_facebook_secret, encrypt_facebook_secret
from core.organizations import get_org_id_for_user


async def get_facebook_meta_row(user_id: str) -> dict:
    """Return the user's Facebook integration row with server-side tokens decoded.

    Preserve the legacy fail-soft contract for missing privileged configuration,
    missing rows, malformed JSON text, and Supabase HTTP rejections. Transport
    failures continue to propagate to callers.
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

    if meta.get("user_token"):
        meta["user_token"] = decrypt_facebook_secret(meta["user_token"])
    return {
        "page_token": decrypt_facebook_secret(row.get("api_key", "")),
        "meta": meta,
    }


async def patch_facebook_meta(
    user_id: str,
    updates: dict,
    new_page_token: str | None = None,
) -> None:
    """Merge Facebook metadata and re-encrypt credentials on every rewrite.

    Preserve the legacy write contract: Supabase HTTP rejections are ignored,
    while transport failures still propagate to the caller.
    """
    cur = await get_facebook_meta_row(user_id)
    meta = cur.get("meta") or {}
    meta.update(updates)
    if meta.get("user_token"):
        meta["user_token"] = encrypt_facebook_secret(meta["user_token"])
    page_token = (
        new_page_token
        if new_page_token is not None
        else cur.get("page_token", "")
    )
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": encrypt_facebook_secret(page_token),
        "meta": json.dumps(meta),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        pass
