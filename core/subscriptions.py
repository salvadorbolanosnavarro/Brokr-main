"""Canonical subscription entitlement checks for Broquer.

Paid-feature access must never depend on importing ``main.py`` or on a
fail-open fallback. This module resolves account state, organization state and
subscription status through shared Core infrastructure.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Request

from core.auth import require_user_id
from core.database import get_rows, patch_rows
from core.organizations import get_org_context, get_org_id_for_user

ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})
INTERNAL_ACCESS_ROLES = frozenset({"equipo", "admin"})


def _not_expired(value: object) -> bool:
    if not value:
        return True
    try:
        expires_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def full_access_grant_active(acceso_completo_hasta) -> bool:
    """Return whether an admin-granted full-access window is still open.

    This is independent from ``rol`` (equipo/admin) and from any Stripe
    subscription: an admin can hand any account paid-feature access through
    a specific end date without making them part of the internal team.
    Unlike ``_not_expired`` — used for columns where an empty value means
    "no limit" — a missing value here means no grant exists at all, so it
    must return ``False`` rather than fail open.
    """
    if not acceso_completo_hasta:
        return False
    try:
        expires_at = datetime.fromisoformat(str(acceso_completo_hasta).replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def trial_has_expired(trial_hasta) -> bool:
    """Preserve the legacy trial expiration parser used by status endpoints."""
    try:
        return datetime.fromisoformat(str(trial_hasta).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except Exception:
        return False


async def expire_trial_subscription(sub_id) -> None:
    """Best-effort persistence after a trial is already considered expired."""
    if not sub_id:
        return
    try:
        await patch_rows(
            "suscripciones",
            {"id": f"eq.{sub_id}"},
            {"status": "expired", "updated_at": datetime.utcnow().isoformat()},
            timeout=8,
        )
    except Exception:
        pass


async def find_latest_subscription(
    user_id: str,
    org_id: Optional[str],
    *,
    select: str = "*",
    timeout: httpx.Timeout | float = 8,
) -> Optional[dict[str, Any]]:
    """Return the most recent ``suscripciones`` row visible to this account.

    A user without an organization yet must still be found by ``user_id`` —
    filtering by ``org_id`` alone when it is ``None`` builds an ``eq.None``
    PostgREST filter that Supabase rejects with 400, which silently hides a
    real, active subscription recorded directly against the user. Once an
    org exists, match either ``org_id`` or ``user_id`` so a subscription
    created before the account joined an org is not lost, and keep only the
    most recently updated row.
    """
    if org_id:
        filters: dict[str, Any] = {"or": f"(org_id.eq.{org_id},user_id.eq.{user_id})"}
    else:
        filters = {"user_id": f"eq.{user_id}"}
    filters.update({"select": select, "order": "updated_at.desc", "limit": "1"})
    rows = await get_rows("suscripciones", filters, timeout=timeout)
    return rows[0] if rows else None


async def has_paid_feature_access(user_id: str) -> bool:
    """Return whether a user may access Broquer paid features.

    The check is deliberately fail-closed: missing configuration, database
    errors, unknown/missing membership or malformed expiration data never grant
    paid access by accident. Internal ``equipo``/``admin`` roles remain exempt,
    matching the existing product behavior.
    """
    if not user_id:
        return False

    try:
        users = await get_rows(
            "usuarios",
            {
                "id": f"eq.{user_id}",
                "select": "rol,activo,acceso_completo_hasta",
                "limit": "1",
            },
            timeout=8,
        )
        if not users:
            return False

        user = users[0]
        if user.get("activo") is False:
            return False
        if (user.get("rol") or "agente") in INTERNAL_ACCESS_ROLES:
            return True
        if full_access_grant_active(user.get("acceso_completo_hasta")):
            return True

        context = await get_org_context(user_id)
        if not context:
            return False

        if context.get("org_tipo") == "empresa":
            return bool(context.get("org_activo", True)) and _not_expired(
                context.get("vence_el")
            )

        org_id = await get_org_id_for_user(user_id)
        subscription = await find_latest_subscription(
            user_id, org_id, select="status", timeout=10
        )
        return bool(
            subscription and subscription.get("status") in ACTIVE_SUBSCRIPTION_STATUSES
        )
    except Exception:
        return False


async def require_paid_feature_access(
    request: Request,
    *,
    detail: str = "Esta función requiere una suscripción activa de Broquer Max.",
) -> str:
    """Authenticate a request and require paid-feature entitlement.

    Returns the trusted user id so domain routers can replace local
    ``_uid_max``-style wrappers with one shared call. Authentication remains
    ``401``; a valid session without entitlement remains ``402``.
    """
    user_id = await require_user_id(request, detail="Inicia sesión para continuar.")
    if not await has_paid_feature_access(user_id):
        raise HTTPException(status_code=402, detail=detail)
    return user_id
