from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows, patch_rows


router = APIRouter()


def _stripe_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.stripe_secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


@router.post("/subscription/cancel")
async def subscription_cancel(request: Request):
    """Cancela la suscripción activa del usuario al final del período actual (at_period_end)."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe no configurado.")

    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    try:
        subscription_rows = await get_rows(
            "suscripciones",
            {"user_id": f"eq.{user_id}", "select": "stripe_subscription_id,status", "order": "updated_at.desc", "limit": "1"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        subscription_rows = []
    row = subscription_rows[0] if subscription_rows else {}
    subscription_id = row.get("stripe_subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=404, detail="No se encontró suscripción activa.")

    async with httpx.AsyncClient(timeout=10) as client:
        r_cancel = await client.post(
            f"https://api.stripe.com/v1/subscriptions/{subscription_id}",
            headers=_stripe_headers(),
            data={"cancel_at_period_end": "true"},
        )
    if r_cancel.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Error al cancelar: {r_cancel.text}")

    try:
        await patch_rows(
            "suscripciones",
            {"user_id": f"eq.{user_id}"},
            {"status": "canceled", "updated_at": datetime.utcnow().isoformat()},
            prefer="return=minimal",
            timeout=8,
        )
    except httpx.HTTPStatusError:
        pass

    return {"ok": True, "message": "Suscripción cancelada correctamente."}
