from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.database import (
    get_service_json_or_empty,
    patch_rows,
    patch_rows_ignoring_http_status,
    post_rows,
)
from core.stripe import (
    EMPRESA_ASIENTOS_BASE,
    STRIPE_WEBHOOK_SECRET,
    activate_enterprise_subscription,
)
from routers.organizaciones import get_org_id_for_user


router = APIRouter()


@router.post("/subscription/webhook")
async def stripe_webhook(request: Request):
    """Process the legacy Stripe subscription webhook contract."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        print("[stripe] STRIPE_WEBHOOK_SECRET no configurado: webhook cerrado.")
        raise HTTPException(status_code=503, detail="Webhook no disponible.")
    if STRIPE_WEBHOOK_SECRET:
        try:
            import hmac as _hmac, hashlib as _hashlib, time as _time
            parts = {p.split("=")[0]: p.split("=")[1] for p in sig_header.split(",") if "=" in p}
            ts = parts.get("t", "")
            v1 = parts.get("v1", "")
            signed_payload = f"{ts}.{payload.decode()}"
            expected = _hmac.new(
                STRIPE_WEBHOOK_SECRET.encode(),
                signed_payload.encode(),
                _hashlib.sha256,
            ).hexdigest()
            if not _hmac.compare_digest(expected, v1):
                raise HTTPException(status_code=400, detail="Firma de webhook inválida.")
        except Exception:
            raise HTTPException(status_code=400, detail="Error verificando webhook.")

    event = await request.json()
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        meta = obj.get("metadata", {}) or {}
        user_id = meta.get("user_id")
        plan_id = meta.get("plan_id", "max")
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if user_id and subscription_id:
            plan_nombre = {"ampi": "AMPI", "empresas": "Broquer para Empresas"}.get(
                plan_id, "Broquer Max"
            )
            org_id = meta.get("org_id") or await get_org_id_for_user(user_id)
            es_trial = meta.get("trial") == "1"
            row = {
                "user_id": user_id,
                "org_id": org_id,
                "plan_id": plan_id,
                "plan_nombre": plan_nombre,
                "stripe_subscription_id": subscription_id,
                "stripe_customer_id": customer_id,
                "status": "trialing" if es_trial else "active",
                "updated_at": datetime.utcnow().isoformat(),
            }
            if es_trial:
                await patch_rows_ignoring_http_status(
                    "usuarios",
                    {"id": f"eq.{user_id}"},
                    {"trial_max_usado": True},
                )
            if plan_id == "empresas":
                try:
                    asientos = int(meta.get("asientos") or EMPRESA_ASIENTOS_BASE)
                except Exception:
                    asientos = EMPRESA_ASIENTOS_BASE
                row["periodo"] = meta.get("periodo") or "mensual"
                row["asientos"] = asientos
                if org_id:
                    await activate_enterprise_subscription(
                        org_id,
                        user_id,
                        asientos,
                        meta.get("nombre_empresa") or "",
                    )
            try:
                await post_rows(
                    "suscripciones",
                    row,
                    prefer="resolution=merge-duplicates,return=minimal",
                    timeout=10,
                )
            except httpx.HTTPStatusError:
                pass

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription_id = obj.get("id")
        new_status = obj.get("status", "canceled")
        if event_type == "customer.subscription.deleted":
            new_status = "canceled"
        if subscription_id:
            try:
                await patch_rows(
                    "suscripciones",
                    {"stripe_subscription_id": f"eq.{subscription_id}"},
                    {"status": new_status, "updated_at": datetime.utcnow().isoformat()},
                    prefer="return=minimal",
                    timeout=8,
                )
            except httpx.HTTPStatusError:
                pass
            rows = await get_service_json_or_empty(
                "suscripciones",
                {
                    "stripe_subscription_id": f"eq.{subscription_id}",
                    "select": "org_id,plan_id",
                    "limit": "1",
                },
            )
            row = rows[0] if rows else {}
            if row.get("plan_id") == "empresas" and row.get("org_id"):
                await patch_rows_ignoring_http_status(
                    "organizaciones",
                    {"id": f"eq.{row['org_id']}"},
                    {
                        "activo": new_status in ("active", "trialing"),
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )

    elif event_type == "invoice.payment_failed":
        subscription_id = obj.get("subscription")
        if subscription_id:
            try:
                await patch_rows(
                    "suscripciones",
                    {"stripe_subscription_id": f"eq.{subscription_id}"},
                    {"status": "past_due", "updated_at": datetime.utcnow().isoformat()},
                    prefer="return=minimal",
                    timeout=8,
                )
            except httpx.HTTPStatusError:
                pass

    return {"ok": True}
