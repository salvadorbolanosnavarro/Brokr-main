"""Canonical request authentication for Broquer.

All backend modules should use these helpers instead of implementing their own
Supabase `/auth/v1/user` calls.
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import HTTPException, Request, status

from core.config import settings


async def get_user_id_from_token(request: Request) -> Optional[str]:
    """Return the authenticated and application-active Supabase user id.

    Supabase validates the bearer token first. Broquer then enforces its own
    ``usuarios.activo`` flag with Service Role because disabling an application
    account does not automatically revoke already-issued Supabase sessions.
    Any uncertainty in that second authorization check fails closed.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    if not settings.supabase_url or not settings.supabase_anon_key:
        return None

    token = auth[7:].strip()
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {token}",
                },
            )
            if response.status_code != 200:
                return None

            try:
                user_id = response.json().get("id")
            except ValueError:
                return None
            if not isinstance(user_id, str) or not user_id:
                return None

            # Application-level authorization. This deliberately uses the
            # privileged key: RLS must not let a user hide their own disabled
            # flag from the server-side access decision.
            if not settings.supabase_service_key:
                return None
            active_response = await client.get(
                f"{settings.supabase_url}/rest/v1/usuarios",
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                },
                params={
                    "id": f"eq.{user_id}",
                    "select": "activo",
                    "limit": "1",
                },
            )
    except httpx.HTTPError:
        return None

    if active_response.status_code != 200:
        return None
    try:
        rows = active_response.json()
    except ValueError:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    if rows[0].get("activo") is False:
        return None
    return user_id


async def require_user_id(
    request: Request,
    *,
    detail: str = "Sesión requerida.",
) -> str:
    """Return active user id or raise a consistent HTTP 401 response."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )
    return user_id
