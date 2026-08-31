"""Read-only Facebook connection status extracted from legacy main.py."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows
from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES, facebook_token_state


router = APIRouter()


@router.get("/facebook/connection")
async def facebook_get_connection(request: Request):
    """Return browser-safe Facebook connection state without exposing tokens."""
    user_id = await get_user_id_from_token(request)
    if not user_id or not settings.supabase_url or not settings.supabase_anon_key:
        return {"connected": False}
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "eq.facebook",
                "select": "api_key,meta",
                "limit": "1",
            },
            timeout=8,
        )
        if rows and rows[0].get("api_key"):
            meta_str = rows[0].get("meta", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
            except Exception:
                meta = {}
            estado_token = facebook_token_state(meta)
            return {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "page_pic": meta.get("page_pic", ""),
                "tiene_token_ads": bool(meta.get("user_token")),
                "ad_account_id": meta.get("ad_account_id", ""),
                "ad_account_name": meta.get("ad_account_name", ""),
                "token": estado_token,
                "scopes_faltantes": [
                    scope for scope in FACEBOOK_REQUIRED_SCOPES
                    if scope not in (meta.get("scopes") or [])
                ] if meta.get("scopes") else [],
            }
    except Exception:
        pass
    return {"connected": False}
