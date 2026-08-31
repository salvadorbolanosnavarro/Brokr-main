"""Facebook geographic targeting search."""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_request


router = APIRouter()


@router.get("/facebook/city-search")
async def facebook_city_search(request: Request, q: str = ""):
    """Busca ciudades/regiones en Meta para targeting geográfico."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    if len(q) < 2:
        return {"results": []}
    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")

    base_params = {
        "type": "adgeolocation",
        "q": q,
        "country_code": "MX",
        "limit": "10",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await _fb_request(
                client,
                "GET",
                "search",
                token=user_token,
                params={**base_params, "location_types": json.dumps(["city", "region"])},
            )
            if r is None or r.status_code != 200:
                r = await _fb_request(
                    client,
                    "GET",
                    "search",
                    token=user_token,
                    params=base_params,
                )
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo conectar con Facebook. Intenta de nuevo.")

    if r is None:
        raise HTTPException(status_code=504, detail="Facebook no respondió al buscar ciudades. Intenta de nuevo.")
    if r.status_code != 200:
        try:
            _msg = r.json().get("error", {}).get("message", "")
        except Exception:
            _msg = ""
        raise HTTPException(
            status_code=502,
            detail=(
                f"Facebook no pudo buscar ciudades: {_msg}"
                if _msg
                else "Facebook no pudo buscar ciudades. Reconecta tu cuenta desde tu perfil."
            ),
        )

    allowed = {"city", "region", "neighborhood", "subcity"}
    results = []
    for d in r.json().get("data", []):
        if not d.get("key") or not d.get("name"):
            continue
        if d.get("type") and d["type"] not in allowed:
            continue
        results.append(
            {
                "key": d["key"],
                "name": d["name"],
                "type": d.get("type", ""),
                "region": d.get("region", ""),
                "country_name": d.get("country_name", ""),
            }
        )
    return {"results": results}
