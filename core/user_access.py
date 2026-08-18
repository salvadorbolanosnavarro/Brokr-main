"""Shared user role and access-state lookups.

These helpers preserve main.py's historical fail-soft defaults while moving the
cross-cutting responsibility into Core. Database I/O remains centralized in
``core.database``.
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
    """Return legacy ``rol`` + ``activo`` state with the exact fail-soft defaults."""
    default = {"rol": "agente", "activo": True}
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return default
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol,activo", "limit": "1"},
            timeout=8,
        )
        if rows:
            return {
                "rol": rows[0].get("rol") or "agente",
                "activo": rows[0].get("activo") if rows[0].get("activo") is not None else True,
            }
    except Exception:
        pass
    return default
