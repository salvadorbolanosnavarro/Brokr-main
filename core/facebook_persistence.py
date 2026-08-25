"""Shared Facebook persistence compatibility helpers.

These helpers preserve the legacy fail-soft contract around optional Facebook
migration tables while keeping the one-time migration warning process-wide.
"""
from __future__ import annotations

import logging


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
