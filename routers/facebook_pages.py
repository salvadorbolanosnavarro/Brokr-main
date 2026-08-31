"""Read-only Facebook page discovery for an authenticated Broquer user."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta_row
from core.facebook_graph import _fb_paginate


router = APIRouter()


@router.get("/facebook/pages")
async def facebook_list_pages(request: Request):
    """Lista TODAS las páginas que el usuario administra (sin reconectar FB)."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    row = await get_facebook_meta_row(user_id)
    user_token = (row.get("meta") or {}).get("user_token", "")
    if not user_token:
        raise HTTPException(
            status_code=400,
            detail="Reconecta tu Facebook para habilitar el cambio de página.",
        )
    async with httpx.AsyncClient(timeout=15) as client:
        data = await _fb_paginate(
            client,
            "me/accounts",
            token=user_token,
            params={"fields": "id,name,access_token,picture.type(square)", "limit": "100"},
            prefix="Error leyendo tus páginas",
        )
    pages = [
        {
            "id": p.get("id", ""),
            "name": p.get("name", p.get("id", "")),
            "picture": ((p.get("picture") or {}).get("data") or {}).get("url", ""),
        }
        for p in data
        if p.get("id")
    ]
    active_id = (row.get("meta") or {}).get("page_id", "")
    return {"pages": pages, "active_page_id": active_id}
