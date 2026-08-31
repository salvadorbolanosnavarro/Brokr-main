"""Canonical administrator authorization for Broquer.

Admin-facing routers should depend on this module rather than implementing
Supabase token validation and role checks independently.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from core.auth import require_user_id
from core.database import get_rows


async def require_admin(request: Request) -> str:
    """Return the authenticated user id only when the user has admin role.

    Authentication and privileged database failures are fail-closed: callers do
    not silently gain administrative access when Supabase is unavailable or
    misconfigured.
    """
    user_id = await require_user_id(request, detail="No autenticado.")
    try:
        rows = await get_rows(
            "usuarios",
            params={
                "id": f"eq.{user_id}",
                "select": "rol",
                "limit": "1",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="No se pudo verificar el acceso administrativo.") from exc

    if not rows or (rows[0].get("rol") or "") != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    return user_id
