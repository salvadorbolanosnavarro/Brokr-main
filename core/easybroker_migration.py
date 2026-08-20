"""Shared in-memory state for EasyBroker migration workflows."""
from __future__ import annotations


MIGRACIONES: dict = {}
PROGRESO_IMPORT: dict = {}


def set_import_progress(user_id: str, texto: str) -> None:
    """Preserve the legacy best-effort granular progress update."""
    try:
        PROGRESO_IMPORT[user_id] = texto
    except Exception:
        pass


def migration_key(org_id, user_id):
    return f"org:{org_id}" if org_id else f"user:{user_id}"
