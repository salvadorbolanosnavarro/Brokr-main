"""Facebook page selection for an authorized Broquer organization member."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.facebook_connection_store import get_facebook_meta_row, patch_facebook_meta
from core.facebook_graph import _fb_paginate
from routers.organizaciones import exigir_gestion_integraciones


router = APIRouter()


class FbSelectPageRequest(BaseModel):
    page_id: str


@router.post("/facebook/select-page")
async def facebook_select_page(req: FbSelectPageRequest, request: Request):
    """Cambia la página activa de la empresa (sin re-OAuth)."""
    user_id = await exigir_gestion_integraciones(request)
    row = await get_facebook_meta_row(user_id)
    user_token = (row.get("meta") or {}).get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    async with httpx.AsyncClient(timeout=10) as client:
        paginas = await _fb_paginate(
            client,
            "me/accounts",
            token=user_token,
            params={"fields": "id,name,access_token", "limit": "100"},
            prefix="Error leyendo tus páginas",
        )

    target = next((p for p in paginas if p.get("id") == req.page_id), None)
    if not target:
        raise HTTPException(
            status_code=400,
            detail="No administras esa página o ya no es accesible.",
        )

    page_token = target.get("access_token", "")
    page_name = target.get("name", req.page_id)
    await patch_facebook_meta(
        user_id,
        {"page_id": req.page_id, "page_name": page_name},
        new_page_token=page_token,
    )
    return {"ok": True, "page_id": req.page_id, "page_name": page_name}
