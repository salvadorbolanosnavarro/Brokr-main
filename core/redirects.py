"""Trusted browser redirect helpers for server-created payment sessions."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from core.config import settings


def _origin(url: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit((url or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            return None
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), port
    except (TypeError, ValueError):
        return None


def trusted_frontend_origins() -> set[tuple[str, str, int | None]]:
    values = {
        settings.app_url,
        settings.frontend_url,
        settings.legacy_main_frontend_url,
        "https://navarroai.github.io",
    }
    return {item for value in values if (item := _origin(value)) is not None}


def checkout_redirect(candidate: str, *, default_base: str, default_path: str) -> str:
    """Return candidate only when its origin is a configured Broquer frontend."""
    raw = (candidate or "").strip()
    if not raw:
        return default_base.rstrip("/") + "/" + default_path.lstrip("/")

    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="URL de retorno inválida.") from exc
    if _origin(raw) not in trusted_frontend_origins():
        raise HTTPException(status_code=400, detail="URL de retorno no permitida.")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL de retorno no permitida.")
    return urlunsplit(parsed)
