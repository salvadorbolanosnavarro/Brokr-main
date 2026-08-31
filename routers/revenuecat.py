import hmac
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.database import post_rows
from core.legacy_main_config import legacy_main_settings
from core.organizations import get_org_id_for_user


router = APIRouter()


@router.post("/subscription/revenuecat-webhook")
async def revenuecat_webhook(request: Request):
    """Procesa cambios de suscripción IAP reportados por RevenueCat."""
    expected_auth = legacy_main_settings.revenuecat_webhook_auth
    if not expected_auth:
        print("[revenuecat] REVENUECAT_WEBHOOK_AUTH no configurado: webhook cerrado.")
        raise HTTPException(status_code=503, detail="Webhook no disponible.")
    if not hmac.compare_digest(str(request.headers.get("Authorization", "")), str(expected_auth)):
        raise HTTPException(status_code=403, detail="No autorizado.")

    body = await request.json()
    event = body.get("event", {}) or {}
    event_type = event.get("type", "")
    user_id = event.get("app_user_id") or event.get("original_app_user_id")
    if not user_id:
        return {"ok": True, "skipped": "sin app_user_id"}

    active_events = {
        "INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION",
        "NON_RENEWING_PURCHASE", "SUBSCRIPTION_EXTENDED",
    }
    if event_type in active_events:
        new_status = "active"
    elif event_type == "EXPIRATION":
        new_status = "expired"
    elif event_type == "BILLING_ISSUE":
        new_status = "past_due"
    elif event_type == "CANCELLATION":
        return {"ok": True, "noted": "cancelacion_programada", "user_id": user_id}
    else:
        return {"ok": True, "ignored": event_type}

    row = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": "max",
        "plan_nombre": "Broquer Max",
        "status": new_status,
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

    return {"ok": True, "user_id": user_id, "status": new_status, "event": event_type}
