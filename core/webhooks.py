"""Shared webhook authentication helpers for Broquer."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request


def require_shared_secret(
    request: Request,
    expected_secret: str,
    *,
    header_name: str = "x-broquer-token",
    query_name: str | None = "token",
    missing_config_detail: str = "Webhook no configurado.",
    invalid_detail: str = "Token inválido.",
) -> None:
    """Require a configured shared secret and compare it in constant time.

    Missing server configuration is a 503 instead of an implicit public
    webhook. Query-string fallback is supported only for backwards
    compatibility and can be disabled by passing ``query_name=None``.
    """
    expected = (expected_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail=missing_config_detail)

    received = request.headers.get(header_name, "")
    if not received and query_name:
        received = request.query_params.get(query_name, "")

    if not received or not hmac.compare_digest(str(received), expected):
        raise HTTPException(status_code=401, detail=invalid_detail)
