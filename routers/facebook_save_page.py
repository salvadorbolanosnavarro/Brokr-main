"""Persist the organization Facebook Page connection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.database import post_rows
from core.facebook_graph import _fb_paginate, _fb_request
from core.facebook_secrets import encrypt_facebook_secret
from core.facebook_token_lifecycle import (
    FB_TOKEN_DEFAULT_LIFETIME_SECONDS,
    debug_facebook_token,
)
from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES
from routers.organizaciones import exigir_gestion_integraciones, get_org_id_for_user

router = APIRouter()


class FbSavePageRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    user_token: str = ""
    token_expires_at: str = ""


@router.post("/facebook/save-page")
async def facebook_save_page(req: FbSavePageRequest, request: Request):
    """Guarda la página de la empresa y auto-selecciona una cuenta publicitaria."""
    user_id = await exigir_gestion_integraciones(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="Supabase no configurado")

    token_expires_at = (req.token_expires_at or "").strip()
    scopes: list = []
    if req.user_token:
        try:
            async with httpx.AsyncClient(timeout=10) as token_client:
                info = await debug_facebook_token(token_client, req.user_token)
            scopes = info.get("scopes") or []
            expires_at = info.get("expires_at")
            if not token_expires_at and expires_at:
                token_expires_at = datetime.fromtimestamp(
                    int(expires_at), timezone.utc
                ).isoformat()
            elif not token_expires_at and info.get("data_access_expires_at"):
                token_expires_at = datetime.fromtimestamp(
                    int(info["data_access_expires_at"]), timezone.utc
                ).isoformat()
        except Exception:
            pass
    if not token_expires_at:
        token_expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=FB_TOKEN_DEFAULT_LIFETIME_SECONDS)
        ).isoformat()

    ad_account_id = ""
    ad_account_name = ""
    page_pic = ""
    try:
        async with httpx.AsyncClient(timeout=15) as account_client:
            try:
                picture_response = await _fb_request(
                    account_client,
                    "GET",
                    req.page_id,
                    token=req.user_token,
                    params={"fields": "picture.type(square)"},
                )
                if picture_response is not None and picture_response.status_code == 200:
                    page_pic = (
                        ((picture_response.json().get("picture") or {}).get("data") or {}).get(
                            "url", ""
                        )
                    )
            except Exception:
                page_pic = ""

            accounts_raw = await _fb_paginate(
                account_client,
                "me/adaccounts",
                token=req.user_token,
                params={"fields": "id,name,account_status,currency", "limit": "50"},
                prefix="Error leyendo cuentas publicitarias",
            )
            accounts = [account for account in accounts_raw if account.get("account_status") == 1]

            chosen = None
            for account in accounts:
                try:
                    pages = await _fb_paginate(
                        account_client,
                        f"{account['id']}/promote_pages",
                        token=req.user_token,
                        params={"fields": "id", "limit": "100"},
                        prefix="Error leyendo páginas promocionables",
                    )
                    if req.page_id in [page.get("id") for page in pages if page.get("id")]:
                        chosen = account
                        break
                except Exception:
                    continue
            if not chosen and accounts:
                chosen = accounts[0]
            if chosen:
                ad_account_id = chosen.get("id", "")
                ad_account_name = chosen.get("name", ad_account_id)
    except Exception:
        pass

    meta = {
        "page_id": req.page_id,
        "page_name": req.page_name,
        "page_pic": page_pic,
        "user_token": encrypt_facebook_secret(req.user_token),
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
        "token_expires_at": token_expires_at,
        "scopes": scopes,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "facebook",
        "api_key": encrypt_facebook_secret(req.page_token),
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

    return {
        "ok": True,
        "page_id": req.page_id,
        "page_name": req.page_name,
        "ad_account_id": ad_account_id,
        "ad_account_name": ad_account_name,
        "token_expires_at": token_expires_at,
        "scopes_faltantes": [scope for scope in FACEBOOK_REQUIRED_SCOPES if scope not in scopes]
        if scopes
        else [],
    }
