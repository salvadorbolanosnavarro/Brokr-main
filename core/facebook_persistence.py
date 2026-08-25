"""Shared Facebook Ads persistence and migration compatibility helpers."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

import httpx

from core.config import settings
from core.database import get_rows, patch_rows, post_rows


FACEBOOK_AD_ENTITIES_TABLE = "fb_ad_entities"
_migration_warning_emitted = False
_log = logging.getLogger("broquer.facebook")


def facebook_table_missing(response) -> bool:
    """Return True only for the historical PostgREST missing-table responses."""
    if response is None:
        return False
    if response.status_code not in (404, 400):
        return False
    text = (response.text or "").lower()
    return (
        "does not exist" in text
        or "could not find the table" in text
        or "pgrst205" in text
    )


def warn_facebook_migration(where: str, response=None) -> None:
    """Emit the legacy Facebook Ads migration warning at most once per process."""
    global _migration_warning_emitted
    if not _migration_warning_emitted:
        _log.warning(
            "La tabla %s no existe (en %s). Corre migracion-facebook-ads.sql en "
            "Supabase para habilitar idempotencia, reconciliación y limpieza de "
            "huérfanos. Los anuncios se siguen creando sin ella.",
            FACEBOOK_AD_ENTITIES_TABLE,
            where,
        )
        _migration_warning_emitted = True


async def find_facebook_creation_by_idempotency(user_id: str, idempotency_key: str) -> dict:
    """Return the previous creation with this key, preserving fail-soft behavior."""
    if not settings.supabase_url or not settings.supabase_service_key or not idempotency_key:
        return {}
    try:
        try:
            rows = await get_rows(
                FACEBOOK_AD_ENTITIES_TABLE,
                {
                    "user_id": f"eq.{user_id}",
                    "idempotency_key": f"eq.{idempotency_key}",
                    "limit": "1",
                },
                timeout=10,
            )
        except httpx.HTTPStatusError as exc:
            if facebook_table_missing(exc.response):
                warn_facebook_migration("buscar idempotencia", exc.response)
            return {}
        if rows:
            return rows[0]
    except Exception as exc:
        _log.error("Error buscando idempotencia: %s", exc)
    return {}


async def reserve_facebook_creation(
    user_id: str,
    org_id,
    data: dict,
    idempotency_key: str = "",
) -> dict:
    """Reserve the creation before touching Meta, preserving the legacy contract."""
    if not settings.supabase_url or not settings.supabase_service_key:
        return {"modo": "sin_tabla"}

    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "org_id": org_id,
        "status": "CREANDO",
        **data,
    }
    if idempotency_key:
        row["idempotency_key"] = idempotency_key

    try:
        try:
            rows = await post_rows(
                FACEBOOK_AD_ENTITIES_TABLE,
                row,
                prefer="return=representation",
                timeout=10,
                accepted_statuses=(200, 201),
            )
            return {"modo": "nuevo", "row_id": (rows[0]["id"] if rows else row["id"])}
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if facebook_table_missing(response):
                warn_facebook_migration("reservar creación", response)
                return {"modo": "sin_tabla"}

            if response.status_code == 409 and idempotency_key:
                previous = await find_facebook_creation_by_idempotency(user_id, idempotency_key)
                if previous:
                    return {"modo": "duplicado", "row": previous}

            _log.error(
                "No se pudo registrar la creación en %s: %s %s",
                FACEBOOK_AD_ENTITIES_TABLE,
                response.status_code,
                (response.text or "")[:300],
            )
    except Exception as exc:
        _log.error("Error registrando la creación en %s: %s", FACEBOOK_AD_ENTITIES_TABLE, exc)
    return {"modo": "sin_tabla"}


async def update_facebook_entity(row_id: str, updates: dict) -> None:
    """Update creation bookkeeping; never fail the primary Meta operation."""
    if not row_id or not settings.supabase_url or not settings.supabase_service_key:
        return
    try:
        try:
            await patch_rows(
                FACEBOOK_AD_ENTITIES_TABLE,
                {"id": f"eq.{row_id}"},
                {**updates, "updated_at": datetime.now(timezone.utc).isoformat()},
                timeout=10,
            )
        except httpx.HTTPStatusError as exc:
            if facebook_table_missing(exc.response):
                warn_facebook_migration("actualizar entidad", exc.response)
            else:
                _log.error(
                    "No se pudo actualizar %s: %s %s",
                    FACEBOOK_AD_ENTITIES_TABLE,
                    exc.response.status_code,
                    (exc.response.text or "")[:300],
                )
    except Exception as exc:
        _log.error("Error actualizando %s: %s", FACEBOOK_AD_ENTITIES_TABLE, exc)
