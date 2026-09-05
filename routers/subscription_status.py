import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.organizations import get_org_context, get_org_id_for_user
from core.subscriptions import (
    expire_trial_subscription,
    find_latest_subscription,
    full_access_grant_active,
    trial_has_expired,
)
from core.user_access import get_user_access_state


router = APIRouter()
log = logging.getLogger("broquer.subscription_status")


@router.get("/subscription/status")
async def subscription_status(request: Request):
    """Devuelve el estado actual de la suscripción del usuario."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")

    access = await get_user_access_state(user_id)
    rol = access["rol"]
    activo = access["activo"]

    if not activo:
        return {"active": False, "plan": None, "plan_id": None, "status": "desactivada"}

    if full_access_grant_active(access.get("acceso_completo_hasta")):
        return {
            "active": True,
            "plan": "Acceso completo",
            "plan_id": "acceso-completo",
            "status": "active",
            "acceso_completo_hasta": access.get("acceso_completo_hasta"),
        }

    if rol in ("equipo", "admin"):
        return {"active": True, "plan": "Equipo Interno" if rol == "equipo" else "Admin", "plan_id": rol, "status": "active"}

    ctx = await get_org_context(user_id)
    if ctx and ctx.get("org_tipo") == "empresa":
        vigente = ctx.get("org_activo", True)
        vence = ctx.get("vence_el")
        if vigente and vence:
            try:
                vigente = datetime.fromisoformat(str(vence).replace("Z", "+00:00")) > datetime.now(timezone.utc)
            except Exception:
                pass
        return {
            "active": bool(vigente),
            "plan": ctx.get("org_plan") or "Empresas",
            "plan_id": "empresas",
            "status": "active" if vigente else "vencida",
        }

    org_id = await get_org_id_for_user(user_id)
    try:
        row = await find_latest_subscription(user_id, org_id, timeout=8)
    except httpx.HTTPStatusError as exc:
        log.error(
            "Fallo consultando suscripciones (user_id=%s, org_id=%s): %s",
            user_id, org_id, exc,
        )
        row = None
    if not row:
        return {"active": False, "plan": None, "status": "sin_suscripcion"}

    # El regalo sin tarjeta de 7 días ya no se ofrece a cuentas nuevas, pero
    # una suscripción "trialing" creada antes de retirarlo sigue vigente
    # hasta su propio trial_hasta — no se corta de golpe a media prueba.
    estado = row.get("status")
    activo_sub = estado in ("active", "trialing")
    if estado == "trialing" and row.get("trial_hasta") and trial_has_expired(row.get("trial_hasta")):
        activo_sub = False
        estado = "trial_vencido"
        asyncio.create_task(expire_trial_subscription(row.get("id")))
    return {
        "active": activo_sub,
        "plan": row.get("plan_nombre"),
        "plan_id": row.get("plan_id"),
        "status": estado,
        "trial_hasta": row.get("trial_hasta"),
        "updated_at": row.get("updated_at"),
    }
