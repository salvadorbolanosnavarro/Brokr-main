"""Canonical Supabase Storage helpers for Broquer.

Modules that upload privileged objects must use this layer instead of rebuilding
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


def _service_headers(content_type: str) -> dict[str, str]:
    settings.require_supabase_service()
    return {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }


def public_object_url(bucket: str, path: str) -> str:
    settings.require_supabase_public()
    bucket = _require_bucket(bucket)
    path = _normalize_object_path(path)
    encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
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
    bucket = _require_bucket(bucket)
    path = _normalize_object_path(path)
    encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/{bucket}/{encoded_path}",
            headers=_service_headers(content_type),
            content=content,
        )
    response.raise_for_status()
    return public_object_url(bucket, path)
