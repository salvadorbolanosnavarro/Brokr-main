"""Fail-closed Meta webhook verification helpers for WhatsApp 2."""
from __future__ import annotations

import hmac

from fastapi import Request, Response


def meta_verify_response(request: Request, expected_token: str) -> Response:
    """Validate Meta's GET verification challenge without fail-open config.

    Missing server configuration is 503. Invalid/missing request credentials
    are 403. A valid subscribe challenge preserves the legacy plain-text body.
    """
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
