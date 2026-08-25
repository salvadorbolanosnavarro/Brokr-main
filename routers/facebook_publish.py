"""Legacy Facebook Page publishing endpoint."""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from core.facebook_graph import _fb_exigir_ok, _fb_request

router = APIRouter()


class FbPublishRequest(BaseModel):
    page_id: str
    page_token: str
    message: str
    photo_urls: list[str] = []


@router.post("/facebook/publish")
async def facebook_publish(req: FbPublishRequest):
    """Publica una propiedad en la página de Facebook."""
    photo_ids = []
    async with httpx.AsyncClient(timeout=30) as client:
        for url in req.photo_urls[:10]:
            response = await _fb_request(
                client,
                "POST",
                f"{req.page_id}/photos",
                token=req.page_token,
                json_body={"url": url, "published": False},
            )
            if response is not None and response.status_code in (200, 201):
                photo_id = response.json().get("id")
                if photo_id:
                    photo_ids.append({"media_fbid": photo_id})

        payload: dict = {"message": req.message}
        if photo_ids:
            payload["attached_media"] = photo_ids

        post_response = await _fb_request(
            client,
            "POST",
            f"{req.page_id}/feed",
            token=req.page_token,
            json_body=payload,
        )

    data = _fb_exigir_ok(post_response, "Error publicando en Facebook")
    return {"ok": True, "post_id": data.get("id")}
