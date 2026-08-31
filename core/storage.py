"""Canonical Supabase Storage helpers for Broquer.

Modules that access privileged objects must use this layer instead of rebuilding
service-role headers and storage URLs independently.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from core.config import settings


_BUCKET = re.compile(r"^[A-Za-z0-9._-]+$")


def _require_bucket(bucket: str) -> str:
    if not _BUCKET.fullmatch(bucket):
        raise ValueError("Invalid Supabase Storage bucket name")
    return bucket


def _normalize_object_path(path: str) -> str:
    normalized = path.strip().lstrip("/")
    if not normalized or normalized.endswith("/"):
        raise ValueError("Storage object path must identify a file")
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        raise ValueError("Storage object path contains an invalid segment")
    return normalized


def _encoded_object(bucket: str, path: str) -> tuple[str, str]:
    bucket = _require_bucket(bucket)
    path = _normalize_object_path(path)
    encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
    return bucket, encoded_path


def _service_headers(*, content_type: str | None = None, upsert: bool = False) -> dict[str, str]:
    settings.require_supabase_service()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if upsert:
        headers["x-upsert"] = "true"
    return headers


def public_object_url(bucket: str, path: str) -> str:
    settings.require_supabase_public()
    bucket, encoded_path = _encoded_object(bucket, path)
    return f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{encoded_path}"


async def upload_object(
    bucket: str,
    path: str,
    content: bytes,
    *,
    content_type: str,
    timeout: float = 60,
) -> str:
    """Upload an object using service-role credentials and return its public URL."""
    settings.require_supabase_service()
    bucket, encoded_path = _encoded_object(bucket, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/{bucket}/{encoded_path}",
            headers=_service_headers(content_type=content_type, upsert=True),
            content=content,
        )
    response.raise_for_status()
    return public_object_url(bucket, path)


async def download_object(
    bucket: str,
    path: str,
    *,
    timeout: float = 60,
) -> bytes:
    """Download a private or public object through service-role authorization."""
    settings.require_supabase_service()
    bucket, encoded_path = _encoded_object(bucket, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{settings.supabase_url}/storage/v1/object/{bucket}/{encoded_path}",
            headers=_service_headers(),
        )
    response.raise_for_status()
    return response.content


async def create_signed_object_url(
    bucket: str,
    path: str,
    *,
    expires_in: int,
    timeout: float = 15,
) -> str:
    """Create a short-lived signed URL for a private object."""
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise ValueError("Signed URL expiration must be a positive integer")

    settings.require_supabase_service()
    bucket, encoded_path = _encoded_object(bucket, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/sign/{bucket}/{encoded_path}",
            headers=_service_headers(content_type="application/json"),
            json={"expiresIn": expires_in},
        )
    response.raise_for_status()
    payload = response.json()
    signed = payload.get("signedURL") if isinstance(payload, dict) else None
    if not signed or not isinstance(signed, str):
        raise RuntimeError("Supabase Storage did not return a signed URL")
    if signed.startswith("http://") or signed.startswith("https://"):
        return signed
    if not signed.startswith("/"):
        signed = "/" + signed
    return f"{settings.supabase_url}/storage/v1{signed}"


async def delete_object(
    bucket: str,
    path: str,
    *,
    timeout: float = 20,
    ignore_missing: bool = True,
) -> None:
    """Delete one object through service-role authorization."""
    settings.require_supabase_service()
    bucket, encoded_path = _encoded_object(bucket, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.delete(
            f"{settings.supabase_url}/storage/v1/object/{bucket}/{encoded_path}",
            headers=_service_headers(),
        )
    if ignore_missing and response.status_code == 404:
        return
    response.raise_for_status()


async def delete_objects(
    bucket: str,
    paths: list[str] | tuple[str, ...],
    *,
    timeout: float = 20,
) -> None:
    """Delete several objects in one Supabase Storage request.

    Every path is normalized before it reaches Supabase so callers cannot use
    batch deletion as a way around the traversal protections applied elsewhere.
    """
    settings.require_supabase_service()
    bucket = _require_bucket(bucket)
    normalized = [_normalize_object_path(path) for path in paths if path]
    if not normalized:
        return

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            "DELETE",
            f"{settings.supabase_url}/storage/v1/object/{bucket}",
            headers=_service_headers(content_type="application/json"),
            json={"prefixes": normalized},
        )
    response.raise_for_status()
