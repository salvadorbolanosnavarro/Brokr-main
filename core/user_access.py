"""Shared user role and access-state lookups.

Role lookup remains conservative (never elevates privileges). Access-state
lookup fails closed only when the Supabase query itself is uncertain
(missing configuration, an empty/failed lookup) — that uncertainty must not
reactivate a disabled account. A ``NULL`` ``activo`` column is not
uncertainty: it means the account was never explicitly disabled, so it is
treated as active. Only an explicit ``false`` deactivates the account.
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
    """Return ``rol`` + ``activo`` (+ ``acceso_completo_hasta``) and deny
    access when state is uncertain.

    ``activo`` is ``NULL`` for accounts that were never explicitly disabled,
    so ``NULL`` maps to ``True`` here — matching every other reader of this
    column. Fail-closed only applies when the lookup itself is uncertain:
    missing configuration, no matching row, or the Supabase request failing.

    ``acceso_completo_hasta`` is the expiration of an admin-granted full
    access window that is independent from ``rol`` and from any Stripe
    subscription — see ``core.subscriptions.full_access_grant_active``.
    """
    default = {"rol": "agente", "activo": False, "acceso_completo_hasta": None}
    if not user_id or not settings.supabase_url or not settings.supabase_service_key:
        return default
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol,activo,acceso_completo_hasta", "limit": "1"},
            timeout=8,
        )
        if rows:
            activo = rows[0].get("activo")
            return {
                "rol": rows[0].get("rol") or "agente",
                "activo": True if activo is None else bool(activo),
                "acceso_completo_hasta": rows[0].get("acceso_completo_hasta"),
            }
    except Exception:
        pass
    return default
