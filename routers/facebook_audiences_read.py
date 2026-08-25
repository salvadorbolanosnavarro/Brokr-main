"""Read-only Facebook custom audience listing."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_paginate


router = APIRouter()


@router.get("/facebook/audiences")
async def facebook_audiences_list(request: Request):
    """List custom/lookalike audiences from the connected Meta ad account."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    meta_fb = await get_facebook_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        filas = await _fb_paginate(
            client,
            f"{account_id}/customaudiences",
            token=user_token,
            params={
                "fields": "id,name,subtype,approximate_count_lower_bound,"
                "approximate_count_upper_bound,operation_status,"
                "delivery_status,time_created",
                "limit": "100",
            },
            prefix="Error leyendo tus públicos",
        )

    salida = []
    for a in filas:
        entrega = a.get("delivery_status") or {}
        operacion = a.get("operation_status") or {}
        listo = entrega.get("code") == 200
        salida.append(
            {
                "id": a.get("id", ""),
                "nombre": a.get("name", ""),
                "tipo": a.get("subtype", ""),
                "tamano_min": a.get("approximate_count_lower_bound"),
                "tamano_max": a.get("approximate_count_upper_bound"),
                "listo": listo,
                "estado": entrega.get("description")
                or operacion.get("description")
                or "",
                "creado": a.get("time_created", ""),
            }
        )
    return {"audiences": salida}
