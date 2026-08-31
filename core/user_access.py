"""Shared user role and access-state lookups.

Role lookup remains conservative (never elevates privileges). Access-state
lookup fails closed because database/configuration uncertainty must not reactivate
a disabled account.
"""
from __future__ import annotations

from core.config import settings
from core.database import get_rows


async def get_user_rol(user_id: str) -> str:
    """Return the user's role, defaulting to ``agente`` on lookup failure."""
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return "agente"
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol", "limit": "1"},
            timeout=8,
        )
        if rows:
            return rows[0].get("rol") or "agente"
    except Exception:
        pass
    return "agente"


async def get_user_access_state(user_id: str) -> dict:
    """Return ``rol`` + ``activo`` and deny access when state is uncertain."""
    default = {"rol": "agente", "activo": False}
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return default
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol,activo", "limit": "1"},
            timeout=8,
        )
        if rows:
            activo = rows[0].get("activo")
            return {
                "rol": rows[0].get("rol") or "agente",
                "activo": bool(activo) if activo is not None else False,
            }
    except Exception:
        pass
    return default
