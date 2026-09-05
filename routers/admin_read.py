"""Legacy admin read endpoints extracted from main.py."""
import httpx
from fastapi import APIRouter, HTTPException, Request

from core.database import get_rows
from core.legacy_admin import require_legacy_admin
from core.subscriptions import full_access_grant_active


router = APIRouter()


@router.get("/admin/me")
async def admin_me(request: Request):
    await require_legacy_admin(request)
    return {"ok": True, "rol": "admin"}


@router.get("/admin/users")
async def admin_list_users(request: Request):
    """Lista usuarios y mezcla la suscripción más reciente por user_id."""
    await require_legacy_admin(request)

    try:
        users = await get_rows(
            "usuarios",
            {
                "select": "id,email,nombre,telefono,rol,activo,created_at,modulos_desactivados,acceso_completo_hasta",
                "order": "created_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")

    try:
        subs = await get_rows(
            "suscripciones",
            {
                "select": "user_id,plan_id,plan_nombre,status,updated_at",
                "order": "updated_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError:
        subs = []

    subs_by_user = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in subs_by_user:
            subs_by_user[uid] = s

    result = []
    for u in users:
        uid = u.get("id")
        sub = subs_by_user.get(uid)
        result.append({
            "id": uid,
            "email": u.get("email"),
            "nombre": u.get("nombre"),
            "telefono": u.get("telefono"),
            "rol": u.get("rol") or "agente",
            "activo": u.get("activo") if u.get("activo") is not None else True,
            "created_at": u.get("created_at"),
            "sub_status": sub.get("status") if sub else None,
            "sub_plan": sub.get("plan_nombre") if sub else None,
            "sub_plan_id": sub.get("plan_id") if sub else None,
            "sub_updated_at": sub.get("updated_at") if sub else None,
            "sub_active": (sub.get("status") in ("active", "trialing")) if sub else False,
            "modulos_desactivados": u.get("modulos_desactivados") or [],
            "acceso_completo_hasta": u.get("acceso_completo_hasta"),
            "acceso_completo_activo": full_access_grant_active(u.get("acceso_completo_hasta")),
        })

    return {"ok": True, "users": result, "count": len(result)}
