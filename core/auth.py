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
    """Return the authenticated Supabase user id, or ``None`` when invalid.

    This preserves the legacy non-raising helper contract so callers can migrate
    incrementally. New protected endpoints should normally use ``require_user_id``.
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
    except httpx.HTTPError:
        return None

    if response.status_code != 200:
        return None

    try:
        user_id = response.json().get("id")
    except ValueError:
        return None

    return user_id if isinstance(user_id, str) and user_id else None


async def require_user_id(request: Request) -> str:
    """Return user id or raise a consistent HTTP 401 response."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión requerida.",
        )
    return user_id
