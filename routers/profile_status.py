import asyncio
import json

from fastapi import APIRouter, Request

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows
from core.facebook_tokens import facebook_token_state
from core.subscriptions import (
    expire_trial_subscription,
    find_latest_subscription,
    full_access_grant_active,
    trial_has_expired,
    trial_max_available,
)
from core.user_access import get_user_rol
from core.organizations import get_org_id_for_user


router = APIRouter()


@router.get("/profile/status")
async def get_profile_status(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
    if not settings.supabase_url or not settings.supabase_service_key:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}

    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "in.(easybroker,facebook)",
                "select": "provider,api_key,meta",
            },
            timeout=8,
        )
    except Exception:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}

    eb_state = {"configured": False, "masked": ""}
    fb_state = {"connected": False}

    for row in rows:
        provider = row.get("provider")
        api_key = row.get("api_key", "")
        if provider == "easybroker" and api_key:
            masked = "*" * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else ""
            eb_state = {"configured": True, "masked": masked}
        elif provider == "facebook" and api_key:
            meta_str = row.get("meta", "{}")
            try:
                meta = json.loads(meta_str) if isinstance(meta_str, str) else (meta_str or {})
            except Exception:
                meta = {}
            fb_state = {
                "connected": True,
                "page_id": meta.get("page_id", ""),
                "page_name": meta.get("page_name", "Página conectada"),
                "tiene_token_ads": bool(meta.get("user_token")),
                "token": facebook_token_state(meta),
            }

    modulos_desactivados = []
    acceso_completo_hasta = None
    try:
        urows = await get_rows(
            "usuarios",
            {
                "id": f"eq.{user_id}",
                "select": "modulos_desactivados,acceso_completo_hasta",
                "limit": "1",
            },
            timeout=8,
        )
        if urows:
            modulos_desactivados = urows[0].get("modulos_desactivados") or []
            acceso_completo_hasta = urows[0].get("acceso_completo_hasta")
    except Exception:
        pass

    sub_state = {"active": False, "plan": None, "status": "sin_suscripcion"}
    try:
        if full_access_grant_active(acceso_completo_hasta):
            sub_state = {
                "active": True,
                "plan": "Acceso completo",
                "status": "active",
            }
        else:
            rol_val = await get_user_rol(user_id)
            if rol_val in ("equipo", "admin"):
                sub_state = {
                    "active": True,
                    "plan": "Equipo Interno" if rol_val == "equipo" else "Admin",
                    "status": "active",
                }
            else:
                org_id = await get_org_id_for_user(user_id)
                row = await find_latest_subscription(user_id, org_id, timeout=6)
                if row:
                    status = row.get("status")
                    active = status in ("active", "trialing")
                    if status == "trialing" and row.get("trial_hasta") and trial_has_expired(row.get("trial_hasta")):
                        active = False
                        status = "trial_vencido"
                        asyncio.create_task(expire_trial_subscription(row.get("id")))
                    sub_state = {
                        "active": active,
                        "plan": row.get("plan_nombre"),
                        "status": status,
                    }
    except Exception:
        pass

    if sub_state.get("status") == "sin_suscripcion":
        try:
            sub_state["trial_disponible"] = await trial_max_available(user_id)
        except Exception:
            sub_state["trial_disponible"] = False

    return {
        "eb": eb_state,
        "fb": fb_state,
        "sub": sub_state,
        "modulos_desactivados": modulos_desactivados,
        "acceso_completo_hasta": acceso_completo_hasta,
    }
