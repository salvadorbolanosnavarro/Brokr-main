"""Per-user module allowlist for Broquer.

An admin can turn specific modules off for one account without touching its
role or its subscription — this is orthogonal to ``core.permissions``
(organization-level permissions) and to ``core.subscriptions`` (paid-feature
entitlement). The canonical key set mirrors the sidebar modules declared in
``app-shell.js`` (``MODS``), minus ``admin`` itself, which is already gated
by role and must never be reachable through this allowlist.
"""
from __future__ import annotations

TOGGLEABLE_MODULES: frozenset[str] = frozenset({
    "props", "contactos", "tareas", "estadisticas", "bolsa",
    "whatsapp", "leads", "correo",
    "contratos", "firmas", "cumplimiento",
    "avm", "isr", "finanzas",
    "image-cleaner", "ficha-manual", "facebook-ads", "video", "mi-sitio",
    "blog", "guia",
})


def normalize_disabled_modules(modulos: list[str] | None) -> list[str]:
    """Return a sorted, de-duplicated list of valid module keys to disable.

    Rejects nothing here — validation of unknown keys is the caller's job
    (it needs to surface a 400 with the offending keys) — this only cleans
    up whitespace/casing noise and duplicates.
    """
    if not modulos:
        return []
    seen = {m.strip() for m in modulos if isinstance(m, str) and m.strip()}
    return sorted(seen)
