import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows
from core.stripe import (
    PROMO_CODE_AMPI,
    STRIPE_PRICE_AMPI,
    STRIPE_PRICE_PRO,
    STRIPE_SECRET_KEY,
    TRIAL_MAX_DIAS,
    get_or_create_stripe_customer,
    stripe_headers,
)
from core.subscriptions import trial_max_available


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key


class CheckoutRequest(BaseModel):
    plan_id: str
    promo_code: str = ""
    success_url: str = ""
    cancel_url: str = ""


@router.post("/subscription/checkout")
async def subscription_checkout(req: CheckoutRequest, request: Request):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe no configurado en el servidor.")

    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    plan_map = {"max": STRIPE_PRICE_PRO, "ampi": STRIPE_PRICE_AMPI}
    if req.plan_id not in plan_map:
        raise HTTPException(status_code=400, detail="Plan inválido.")
    price_id = plan_map[req.plan_id]
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Precio Stripe no configurado para el plan '{req.plan_id}'.")

    if req.plan_id == "ampi":
        if req.promo_code.strip().lower() != PROMO_CODE_AMPI.lower():
            raise HTTPException(status_code=400, detail="Código promocional inválido para el plan AMPI.")

    auth_tok = request.headers.get("Authorization", "")[7:]
    async with httpx.AsyncClient(timeout=10) as client:
        r_user = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth_tok}"},
        )
    if r_user.status_code != 200:
        raise HTTPException(status_code=401, detail="No se pudo verificar el usuario.")
    email = r_user.json().get("email", "")

    try:
        filas_nombre = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "nombre"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        filas_nombre = []
    nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)

    customer_id = await get_or_create_stripe_customer(user_id, email, nombre)

    origin = request.headers.get("origin", "https://navarroai.github.io/Brokr")
    success_url = req.success_url or f"{origin}/index.html?suscripcion=ok"
    cancel_url = req.cancel_url or f"{origin}/index.html?suscripcion=cancelada"

    con_trial = await trial_max_available(user_id)

    data = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[user_id]": user_id,
        "metadata[plan_id]": req.plan_id,
        "allow_promotion_codes": "true",
        "locale": "es",
    }
    if con_trial:
        data["subscription_data[trial_period_days]"] = str(TRIAL_MAX_DIAS)
        data["metadata[trial]"] = "1"

    async with httpx.AsyncClient(timeout=15) as client:
        r_cs = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            headers=stripe_headers(),
            data=data,
        )
    if r_cs.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe checkout session: {r_cs.text}")

    session = r_cs.json()
    return {"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id")}
