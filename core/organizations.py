"""Canonical organization context and authorization helpers for Broquer.

This replaces the cross-cutting pieces currently embedded in
``routers/organizaciones.py``. Domain routers should consume this module rather
than importing another router for authentication/authorization infrastructure.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request, status

from core.auth import require_user_id
from core.database import get_rows
from core.permissions import effective_permission


async def get_org_context(user_id: str) -> Optional[dict[str, Any]]:
    """Return the active organization context for a user, or ``None``.

    Privileged database access is handled by ``core.database`` and therefore
    fails closed if service-role configuration is unavailable.
    """
    if not user_id:
        return None

    members = await get_rows(
        "organizacion_miembros",
        {
            "user_id": f"eq.{user_id}",
            "activo": "eq.true",
            "select": "org_id,rol_org,permisos,activo",
            "limit": "1",
        },
        timeout=10,
    )
    if not members:
        return None

    member = members[0]
    org: dict[str, Any] = {}
    org_id = member.get("org_id")
    if org_id:
        organizations = await get_rows(
            "organizaciones",
            {
                "id": f"eq.{org_id}",
                "select": "nombre,tipo,activo,plan,asientos_max,vence_el",
                "limit": "1",
            },
            timeout=10,
        )
        if organizations:
            org = organizations[0]

    return {
        "org_id": org_id,
        "rol_org": member.get("rol_org") or "agente",
        "permisos": member.get("permisos") or {},
        "activo": bool(member.get("activo")),
        "org_nombre": org.get("nombre"),
        "org_tipo": org.get("tipo") or "personal",
        "org_activo": bool(org.get("activo", True)),
        "org_plan": org.get("plan"),
        "asientos_max": org.get("asientos_max"),
        "vence_el": org.get("vence_el"),
    }


async def get_org_id_for_user(user_id: str) -> Optional[str]:
    context = await get_org_context(user_id)
    return context.get("org_id") if context else None


def has_org_permission(context: dict[str, Any] | None, permission: str) -> bool:
    """Resolve an organization permission and fail closed on invalid context."""
    if not context or not context.get("activo") or not context.get("org_activo", True):
        return False
    try:
        return effective_permission(
            context.get("rol_org") or "agente",
            permission,
            context.get("permisos") or {},
        )
    except ValueError:
        return False


async def require_org_permission(
    request: Request,
    permission: str,
    *,
    unauthorized_detail: str = "Inicia sesión.",
    missing_org_detail: str = "Tu cuenta no está configurada. Contacta a soporte.",
    forbidden_detail: str = "No tienes permiso para realizar esta acción.",
) -> str:
    """Authenticate and authorize one organization permission.

    Any missing dependency, membership, inactive organization, unknown role, or
    unknown permission denies access instead of degrading to authentication-only.
    """
    user_id = await require_user_id(request, detail=unauthorized_detail)

    try:
        context = await get_org_context(user_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo verificar el acceso de tu organización.",
        ) from exc

    if not context:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=missing_org_detail,
        )

    if not has_org_permission(context, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=forbidden_detail,
        )

    return user_id


async def require_integration_management(request: Request) -> str:
    """Authorize organization-level EasyBroker/Meta integration management."""
    return await require_org_permission(
        request,
        "gestionar_integraciones",
        forbidden_detail=(
            "Solo el dueño de la cuenta puede conectar o desconectar EasyBroker "
            "y Facebook. Pídele que te dé el permiso desde Equipo."
        ),
    )
