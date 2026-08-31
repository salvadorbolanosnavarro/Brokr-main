"""EasyBroker colonia autocomplete endpoint."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from core.cache import cache_get, cache_set
from core.easybroker import EB_API_KEY, EB_BASE, eb_headers, extract_colonia, normalize


router = APIRouter()


@router.get("/colonias")
async def get_colonias(q: str = Query("", min_length=2), ciudad: str = "Morelia"):
    """Return unique colonias matching search query — fast direct EB search."""
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")

    cache_key = f"colonias_{normalize(ciudad)}"
    colonias_map = cache_get(cache_key)

    if colonias_map is None:
        colonias_map = {}
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while page <= 80:
                r = await client.get(
                    f"{EB_BASE}/properties",
                    headers=eb_headers(),
                    params={"limit": 50, "page": page},
                )
                if r.status_code != 200:
                    break
                data = r.json()
                props = data.get("content", [])
                if not props:
                    break
                for p in props:
                    loc = p.get("location", "")
                    if not loc or normalize(ciudad) not in normalize(loc):
                        continue
                    col = extract_colonia(loc)
                    if col and len(col) > 2:
                        colonias_map[col] = colonias_map.get(col, 0) + 1
                if not data.get("pagination", {}).get("next_page"):
                    break
                page += 1
        cache_set(cache_key, colonias_map)

    q_norm = normalize(q)
    matches = [
        {"colonia": col, "count": cnt}
        for col, cnt in colonias_map.items()
        if q_norm in normalize(col)
    ]
    matches.sort(key=lambda x: -x["count"])
    return {"colonias": matches[:12], "total_colonias": len(colonias_map)}
