"""Compatibility admin authorization used while main.py is decomposed.

This intentionally preserves main.py's historical 401/403 behavior instead of
using core.admin.require_admin, whose fail-closed database-error semantics are
stricter and therefore not behavior-equivalent.
"""
from fastapi import HTTPException, Request

from core.auth import get_user_id_from_token
from core.user_access import get_user_rol


async def require_legacy_admin(request: Request) -> str:
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado.")
    rol = await get_user_rol(user_id)
    if rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    return user_id
