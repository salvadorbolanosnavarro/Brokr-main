"""Shared Supabase access primitives for Broquer.

Privileged database access is centralized here so domain modules do not build
service-role headers or invent error behavior independently. Explicit public
reads also live here when a legacy flow intentionally relies on Supabase RLS.
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


def public_headers() -> dict[str, str]:
    """Return the public Supabase credentials used by RLS-governed reads."""
    settings.require_supabase_public()
    return {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
        "Content-Type": "application/json",
    }


def rest_url(table: str) -> str:
    settings.require_supabase_public()
    normalized = table.strip().strip("/")
    if not normalized or "/" in normalized:
        raise ValueError("Supabase table name must be a simple identifier")
    return f"{settings.supabase_url}/rest/v1/{normalized}"


async def _get_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    headers: Mapping[str, str],
    timeout: httpx.Timeout | float,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            rest_url(table),
            headers=dict(headers),
            params=dict(params),
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Supabase response for table {table}")
    return payload


async def get_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    return await _get_rows(
        table,
        params,
        headers=service_headers(),
        timeout=timeout,
    )


async def get_public_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Read rows with the public key so Supabase RLS remains authoritative."""
    return await _get_rows(
        table,
        params,
        headers=public_headers(),
        timeout=timeout,
    )


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
) -> list[dict[str, Any]]:
    """Patch rows and return representations when PostgREST sends them.

    Existing callers that only care about success may ignore the returned
    list. Callers using ``Prefer: return=representation`` receive the updated
    rows without rebuilding another PATCH helper.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.patch(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            params=dict(params),
            json=dict(payload),
        )
    response.raise_for_status()
    if not response.content:
        return []
    data = response.json()
    return data if isinstance(data, list) else []


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
