"""Shared Supabase access primitives for Broquer.

Privileged database access is centralized here so domain modules do not build
service-role headers or invent error behavior independently.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from core.config import settings


DEFAULT_TIMEOUT = httpx.Timeout(15.0)


def service_headers(*, prefer: Optional[str] = None) -> dict[str, str]:
    """Return service-role headers, failing closed if config is incomplete."""
    settings.require_supabase_service()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def rest_url(table: str) -> str:
    settings.require_supabase_public()
    normalized = table.strip().strip("/")
    if not normalized or "/" in normalized:
        raise ValueError("Supabase table name must be a simple identifier")
    return f"{settings.supabase_url}/rest/v1/{normalized}"


async def get_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            rest_url(table),
            headers=service_headers(),
            params=dict(params),
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Supabase response for table {table}")
    return payload


async def post_rows(
    table: str,
    payload: Any,
    *,
    prefer: str = "return=representation",
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            json=payload,
        )
    response.raise_for_status()
    if not response.content:
        return []
    data = response.json()
    return data if isinstance(data, list) else []


async def upsert_rows(
    table: str,
    payload: Any,
    *,
    conflict: str,
    prefer: str = "resolution=merge-duplicates,return=representation",
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Upsert rows through PostgREST using an explicit conflict target."""
    conflict = conflict.strip()
    if not conflict or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_," for ch in conflict):
        raise ValueError("Supabase upsert conflict target is invalid")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            rest_url(table),
            params={"on_conflict": conflict},
            headers=service_headers(prefer=prefer),
            json=payload,
        )
    response.raise_for_status()
    if not response.content:
        return []
    data = response.json()
    return data if isinstance(data, list) else []


async def patch_rows(
    table: str,
    params: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    prefer: str = "return=minimal",
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> None:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.patch(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            params=dict(params),
            json=dict(payload),
        )
    response.raise_for_status()


async def delete_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> None:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.delete(
            rest_url(table),
            headers=service_headers(),
            params=dict(params),
        )
    response.raise_for_status()
