"""Canonical organization roles and permission defaults for Broquer.

This module is intentionally free of HTTP/database code. It defines only the
permission vocabulary and deterministic policy so every domain can share the
same rules without duplicating constants.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_AGENT = "agente"

VALID_ORG_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_AGENT})

VALID_PERMISSIONS = frozenset({
    "ver_telefonos",
    "gestionar_integraciones",
    "ver_comisiones",
    "ver_inventario_completo",
    "ver_contactos_equipo",
    "exportar",
    "ver_estadisticas_equipo",
})

_AGENT_DEFAULTS = {
    "ver_telefonos": False,
    "gestionar_integraciones": False,
    "ver_comisiones": False,
    "ver_inventario_completo": True,
    "ver_contactos_equipo": True,
    "exportar": True,
    "ver_estadisticas_equipo": False,
}

AGENT_DEFAULTS: Mapping[str, bool] = MappingProxyType(_AGENT_DEFAULTS)


def default_permission(role: str, permission: str) -> bool:
    """Return the role default for one permission, rejecting unknown values.

    Owners and admins receive organization-management permissions by default;
    agents use the explicit least-privilege matrix above. Per-member overrides
    are applied by the organization service, not here.
    """
    if role not in VALID_ORG_ROLES:
        raise ValueError(f"Unknown organization role: {role}")
    if permission not in VALID_PERMISSIONS:
        raise ValueError(f"Unknown organization permission: {permission}")

    if role in {ROLE_OWNER, ROLE_ADMIN}:
        return True
    return AGENT_DEFAULTS[permission]


def effective_permission(
    role: str,
    permission: str,
    overrides: Mapping[str, object] | None = None,
) -> bool:
    """Resolve a permission using an explicit boolean override when present."""
    base = default_permission(role, permission)
    if not overrides or permission not in overrides:
        return base

    override = overrides[permission]
    if isinstance(override, bool):
        return override
    return base
