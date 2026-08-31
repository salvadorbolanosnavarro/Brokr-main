"""Facebook ad-account discovery for authenticated Broquer users."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_batch, _fb_paginate


router = APIRouter()
_log = logging.getLogger("broquer.facebook")


@router.get("/facebook/ad-accounts")
async def facebook_ad_accounts(request: Request):
    """Devuelve las cuentas publicitarias accesibles por el usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(
            status_code=400,
            detail="Token de usuario sin permisos de ads. Reconecta tu Facebook.",
        )

    async with httpx.AsyncClient(timeout=15) as client:
        accounts = await _fb_paginate(
            client,
            "me/adaccounts",
            token=user_token,
            params={"fields": "id,name,account_status,currency", "limit": "50"},
            prefix="Error leyendo cuentas publicitarias",
        )
    active_raw = [a for a in accounts if a.get("account_status", 0) == 1]

    paginas_por_cuenta: dict = {}
    if active_raw:
        async with httpx.AsyncClient(timeout=30) as client:
            resultados = await _fb_batch(
                client,
                user_token,
                [
                    {
                        "method": "GET",
                        "relative_url": f"{a['id']}/promote_pages?fields=id&limit=100",
                    }
                    for a in active_raw
                ],
            )
            for cuenta, res in zip(active_raw, resultados):
                ids: list[str] = []
                cuerpo = res.get("body")
                if res.get("code") == 200 and isinstance(cuerpo, dict):
                    ids = [p["id"] for p in (cuerpo.get("data") or []) if p.get("id")]
                elif res.get("code") != 200:
                    _log.warning(
                        "promote_pages falló para %s: %s",
                        cuenta.get("id"),
                        str(cuerpo)[:200],
                    )
                paginas_por_cuenta[cuenta["id"]] = ids

    active: list[dict] = []
    for a in active_raw:
        page_ids: list[str] = paginas_por_cuenta.get(a["id"], [])
        active.append(
            {
                "id": a["id"],
                "name": a.get("name", a["id"]),
                "currency": a.get("currency", "MXN"),
                "promote_pages": page_ids,
            }
        )
    return {"accounts": active}
