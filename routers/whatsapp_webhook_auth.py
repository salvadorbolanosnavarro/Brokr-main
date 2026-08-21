"""Fail-closed Meta webhook verification helpers for WhatsApp 2."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Request, Response


def meta_verify_response(request: Request, expected_token: str) -> Response:
    """Validate Meta's GET verification challenge without fail-open config."""
    expected = (expected_token or "").strip()
    if not expected:
        return Response(content="webhook not configured", status_code=503)

    params = request.query_params
    received = params.get("hub.verify_token", "")
    valid = (
        params.get("hub.mode") == "subscribe"
        and bool(received)
        and hmac.compare_digest(str(received), expected)
    )
    if valid:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


def meta_signature_error(raw: bytes, signature: str, app_secret: str) -> Response | None:
    """Return the legacy failure response for invalid POST auth, else ``None``.

    Missing server secret is a configuration failure (503). A missing or bad
    client signature is forbidden (403). Valid signatures are compared in
    constant time and return ``None`` so the caller can continue parsing.
    """
    secret = app_secret or ""
    if not secret:
        return Response(status_code=503)
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature or "", expected):
        return Response(status_code=403)
    return None
