"""Facebook ad-account selection for an authorized Broquer organization member."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.facebook_connection_store import patch_facebook_meta
from routers.organizaciones import exigir_gestion_integraciones


router = APIRouter()


class FbSelectAdAccountRequest(BaseModel):
    account_id: str
    account_name: str = ""


@router.post("/facebook/select-ad-account")
async def facebook_select_ad_account(req: FbSelectAdAccountRequest, request: Request):
    """Recuerda la última cuenta publicitaria elegida.
    Toca dónde se cobran los anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    await patch_facebook_meta(
        user_id,
        {
            "ad_account_id": req.account_id,
            "ad_account_name": req.account_name or req.account_id,
        },
    )
    return {"ok": True, "account_id": req.account_id}
