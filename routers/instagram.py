"""Public Instagram feed for the Broquer landing page."""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException

from core.legacy_main_config import legacy_main_settings


router = APIRouter()
_IG_CACHE = {"t": 0.0, "data": None}


@router.get("/instagram/feed")
async def instagram_feed():
    """Return the latest Instagram posts with the legacy six-hour cache contract."""
    ahora = time.time()
    if _IG_CACHE["data"] is not None and (ahora - _IG_CACHE["t"]) < 21600:
        return _IG_CACHE["data"]

    tok = legacy_main_settings.instagram_token
    ig_id = legacy_main_settings.ig_user_id
    if not tok or not ig_id:
        raise HTTPException(status_code=503, detail="Instagram no configurado")

    url = (
        "https://graph.facebook.com/v25.0/"
        + ig_id
        + "/media"
        "?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
        "&limit=12&access_token="
        + tok
    )
    try:
        async with httpx.AsyncClient(timeout=12) as cli:
            response = await cli.get(url)
        if response.status_code != 200:
            if _IG_CACHE["data"] is not None:
                return _IG_CACHE["data"]
            raise HTTPException(status_code=502, detail="Instagram no respondió")
        crudo = response.json().get("data", [])
    except HTTPException:
        raise
    except Exception:
        if _IG_CACHE["data"] is not None:
            return _IG_CACHE["data"]
        raise HTTPException(status_code=502, detail="Sin conexión con Instagram")

    posts = []
    for post in crudo:
        posts.append(
            {
                "id": post.get("id"),
                "tipo": post.get("media_type"),
                "portada": post.get("thumbnail_url") or post.get("media_url"),
                "liga": post.get("permalink"),
                "texto": (post.get("caption") or "")[:120],
            }
        )

    data = {"ok": True, "posts": posts}
    _IG_CACHE["data"] = data
    _IG_CACHE["t"] = ahora
    return data
