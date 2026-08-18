"""Shared state and predicates for EasyBroker property-photo migration."""
from __future__ import annotations

from core.config import settings


FOTOS_BUCKET = "fotos-propiedades"

# org_id values with an active background migration worker.
fotos_en_proceso: set[str] = set()


def foto_ya_es_de_broquer(url) -> bool:
    """Return True when the URL already belongs to Broquer's Supabase Storage."""
    return isinstance(url, str) and bool(settings.supabase_url) and settings.supabase_url in url


def foto_migrable(url) -> bool:
    """Return True for an external HTTP image URL worth migrating to Broquer."""
    return (
        isinstance(url, str)
        and url.startswith("http")
        and not foto_ya_es_de_broquer(url)
    )
