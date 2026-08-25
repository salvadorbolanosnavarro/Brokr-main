"""Read-only Facebook page post listing."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta_row
from core.facebook_graph import _fb_paginate


router = APIRouter()


@router.get("/facebook/page-posts")
async def facebook_page_posts(request: Request, page_id: str = ""):
    """List the latest posts from a Facebook page available to the user."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    row = await get_facebook_meta_row(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta = row.get("meta") or {}
    user_token = meta.get("user_token", "")

    target_page_id = (page_id or meta.get("page_id", "")).strip()
    if not target_page_id:
        raise HTTPException(status_code=400, detail="No hay página seleccionada.")

    if target_page_id == meta.get("page_id", ""):
        page_token = row.get("page_token", "")
    else:
        if not user_token:
            raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
        async with httpx.AsyncClient(timeout=10) as client:
            paginas = await _fb_paginate(
                client,
                "me/accounts",
                token=user_token,
                params={"fields": "id,access_token", "limit": "100"},
                prefix="No se pudieron resolver las páginas",
            )
        match = next((p for p in paginas if p.get("id") == target_page_id), None)
        if not match:
            raise HTTPException(status_code=400, detail="No administras esa página.")
        page_token = match.get("access_token", "")

    if not page_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")
    page_id = target_page_id

    async with httpx.AsyncClient(timeout=15) as client:
        posts = await _fb_paginate(
            client,
            f"{page_id}/posts",
            token=page_token,
            params={
                "fields": "id,message,created_time,full_picture,permalink_url,"
                "reactions.summary(true),comments.summary(true),shares,is_published",
                "limit": "25",
            },
            max_paginas=1,
            max_items=25,
            prefix="Error obteniendo publicaciones",
        )

    items = []
    for p in posts:
        if p.get("is_published") is False:
            continue
        msg = (p.get("message") or "").strip()
        items.append(
            {
                "id": p["id"],
                "message": msg[:280],
                "created_time": p.get("created_time", ""),
                "image": p.get("full_picture", ""),
                "permalink": p.get("permalink_url", ""),
                "reactions": ((p.get("reactions") or {}).get("summary") or {}).get(
                    "total_count", 0
                ),
                "comments": ((p.get("comments") or {}).get("summary") or {}).get(
                    "total_count", 0
                ),
                "shares": (p.get("shares") or {}).get("count", 0),
                "has_image": bool(p.get("full_picture")),
            }
        )

    return {"posts": items, "page_id": page_id}
