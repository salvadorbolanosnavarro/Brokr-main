import hmac
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.database import get_rows, post_rows
from core.legacy_main_config import legacy_main_settings
from core.organizations import get_org_id_for_user


router = APIRouter()


@router.post("/subscription/activate")
async def subscription_activate(request: Request):
    """Activa una suscripción por customer_id usando el secreto interno de Zapier."""
    activate_secret = legacy_main_settings.activate_secret
    body = await request.json()

    if not activate_secret:
        print("[subscription] ACTIVATE_SECRET no configurado: endpoint cerrado.")
        raise HTTPException(status_code=503, detail="Activación no disponible.")
    if not hmac.compare_digest(str(body.get("secret", "")), str(activate_secret)):
        raise HTTPException(status_code=403, detail="No autorizado.")

    customer_id = body.get("customer_id", "").strip()
    plan_id = body.get("plan_id", "max").strip() or "max"
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id requerido.")

    try:
        users = await get_rows(
            "usuarios",
            {"stripe_customer_id": f"eq.{customer_id}", "select": "id,nombre,email"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        users = []

    if not users:
        raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")

    user = users[0]
    user_id = user["id"]
    plan_name = "AMPI" if plan_id == "ampi" else "Broquer Max"

    row = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": plan_id,
        "plan_nombre": plan_name,
        "stripe_customer_id": customer_id,
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "suscripciones",
            row,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        pass

    return {"ok": True, "user_id": user_id, "plan": plan_name}
