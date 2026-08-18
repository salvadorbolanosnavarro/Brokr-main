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


def rpc_url(function: str) -> str:
    """Build a PostgREST RPC URL for one simple stored-function name."""
    settings.require_supabase_public()
    normalized = function.strip().strip("/")
    if not normalized or "/" in normalized:
        raise ValueError("Supabase RPC function name must be a simple identifier")
    return f"{settings.supabase_url}/rest/v1/rpc/{normalized}"


def _require_response_status(
    response: httpx.Response,
    accepted_statuses: tuple[int, ...] | None = None,
) -> None:
    """Raise when a response violates either HTTP success or an exact legacy set.

    With no explicit set this retains normal httpx semantics: every 2xx status is
    accepted. Callers migrating legacy code that intentionally accepted only a
    subset (for example 200/201 but not 204) may provide that exact set without
    rebuilding HTTP handling outside Core.
    """
    if accepted_statuses is None:
        response.raise_for_status()
        return
    if response.status_code in accepted_statuses:
        return
    if response.is_error:
        response.raise_for_status()
    raise httpx.HTTPStatusError(
        f"Unexpected HTTP status {response.status_code}",
        request=response.request,
        response=response,
    )


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


async def get_service_json(
    table: str,
    params: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    accepted_statuses: tuple[int, ...] | None = None,
) -> Any:
    """GET with service credentials and return decoded JSON without shape coercion.

    This exists for legacy callers whose contract distinguished an exact HTTP
    status but intentionally accepted any valid JSON shape. Transport and JSON
    decoding errors propagate; callers may translate HTTP status errors locally.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            rest_url(table),
            headers=service_headers(),
            params=dict(params),
        )
    _require_response_status(response, accepted_statuses)
    return response.json()


async def call_public_rpc(
    function: str,
    payload: Mapping[str, Any],
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    accepted_statuses: tuple[int, ...] | None = None,
) -> Any:
    """Call a Supabase RPC with public credentials and return its decoded JSON.

    The payload is intentionally returned without shape coercion so migrated
    callers retain their historical JSON semantics. ``accepted_statuses`` can
    pin an exact legacy success set while transport and JSON errors propagate.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            rpc_url(function),
            headers=public_headers(),
            json=dict(payload),
        )
    _require_response_status(response, accepted_statuses)
    return response.json()


async def post_rows(
    table: str,
    payload: Any,
    *,
    prefer: str = "return=representation",
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    accepted_statuses: tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            json=payload,
        )
    _require_response_status(response, accepted_statuses)
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
    accepted_statuses: tuple[int, ...] | None = None,
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
    _require_response_status(response, accepted_statuses)
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
    accepted_statuses: tuple[int, ...] | None = None,
) -> list[dict[str, Any]]:
    """Patch rows and return representations when PostgREST sends them.

    Existing callers that only care about success may ignore the returned
    list. Callers using ``Prefer: return=representation`` receive the updated
    rows without rebuilding another PATCH helper. ``accepted_statuses`` may
    pin an exact legacy status set while the default continues accepting all
    ordinary 2xx responses.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.patch(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            params=dict(params),
            json=dict(payload),
        )
    _require_response_status(response, accepted_statuses)
    if not response.content:
        return []
    data = response.json()
    return data if isinstance(data, list) else []


async def patch_rows_no_response(
    table: str,
    params: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    prefer: str = "return=minimal",
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    accepted_statuses: tuple[int, ...] | None = None,
) -> None:
    """PATCH rows while intentionally ignoring the response body.

    Legacy status-only writes often never parsed the body. This helper keeps
    that contract while still centralizing credentials, URL construction and
    optional exact-status validation.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.patch(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            params=dict(params),
            json=dict(payload),
        )
    _require_response_status(response, accepted_statuses)


async def delete_rows(
    table: str,
    params: Mapping[str, Any],
    *,
    prefer: str | None = None,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    accepted_statuses: tuple[int, ...] | None = None,
) -> None:
    """Delete rows while allowing callers to preserve exact legacy HTTP semantics.

    Existing callers retain the historical default: no Prefer header and any
    ordinary 2xx response accepted. Migrations that depended on a specific
    Prefer value or exact success-status set can make that contract explicit.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.delete(
            rest_url(table),
            headers=service_headers(prefer=prefer),
            params=dict(params),
        )
    _require_response_status(response, accepted_statuses)
