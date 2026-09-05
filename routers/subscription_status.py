import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.database import patch_rows, post_rows
from core.organizations import get_org_context, get_org_id_for_user
from core.subscriptions import (
    expire_trial_subscription,
    find_latest_subscription,
    full_access_grant_active,
    trial_has_expired,
    trial_max_available,
)
from core.user_access import get_user_access_state
from limites import exigir_cupo


router = APIRouter()
log = logging.getLogger("broquer.subscription_status")
TRIAL_MAX_DIAS = 7


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
        return {"active": False, "plan": None, "status": "sin_suscripcion",
                "trial_disponible": await trial_max_available(user_id)}

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
        "trial_disponible": (await trial_max_available(user_id)) if not activo_sub else False,
    }


@router.post("/subscription/trial-max")
async def subscription_trial_max(request: Request):
    """Activa 7 días de Broquer Max sin pedir tarjeta, una sola vez por cuenta."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    exigir_cupo(request, user_id)

    if not await trial_max_available(user_id):
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta ya usó su periodo de prueba de Broquer Max.")

    hasta = datetime.now(timezone.utc) + timedelta(days=TRIAL_MAX_DIAS)
    fila = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "plan_id": "max",
        "plan_nombre": "Broquer Max",
        "status": "trialing",
        "trial_hasta": hasta.isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "suscripciones",
            fila,
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 201),
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")

    try:
        await patch_rows(
            "usuarios",
            {"id": f"eq.{user_id}"},
            {"trial_max_usado": True},
            prefer="return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        pass
    return {"ok": True, "plan": "Broquer Max", "trial_hasta": hasta.isoformat(), "dias": TRIAL_MAX_DIAS}
