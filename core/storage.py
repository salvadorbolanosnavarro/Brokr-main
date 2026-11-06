"""Canonical Supabase Storage helpers for Broquer.

Modules that access privileged objects must use this layer instead of rebuilding
service-role headers and storage URLs independently.
"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote

import httpx

from core.config import settings
from core.file_validation import tipo_guardable


_BUCKET = re.compile(r"^[A-Za-z0-9._-]+$")

# Buckets con datos de clientes. Sus objetos se guardan sin caché pública y se
# leen solo con ligas firmadas de corta duración. ``wa-media`` y
# ``adjuntos-historial`` todavía son públicos en Supabase hasta correr
# sql-manual/20261106-archivos-privados.sql; ya se tratan como privados aquí.
PRIVATE_BUCKETS = frozenset({
    "firmas", "pld-expedientes", "fin-comprobantes", "machotes-contrato",
    "adjuntos-historial", "wa-media",
})
CACHE_PRIVADO = "private, no-store, max-age=0"


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


def _service_headers(*, content_type: str | None = None, upsert: bool = False,
                     cache_control: str | None = None) -> dict[str, str]:
    settings.require_supabase_service()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if upsert:
        headers["x-upsert"] = "true"
    if cache_control:
        headers["cache-control"] = cache_control
    return headers


def cache_control_for(bucket: str) -> str | None:
    """Private buckets never get public caching; public ones keep Supabase's default."""
    return CACHE_PRIVADO if bucket in PRIVATE_BUCKETS else None


def ensure_storable(path: str, content_type: str | None, *, bucket: str = "",
                    server_generated_xml: bool = False) -> None:
    """Nunca se guarda algo que el navegador pueda ejecutar como página web.

    Única excepción: XML que arma el propio servidor (avisos PLD para el SAT),
    solo en buckets privados y servido después como descarga.
    """
    if server_generated_xml:
        if bucket not in PRIVATE_BUCKETS or (content_type or "") != "application/xml" \
                or not path.endswith(".xml"):
            raise ValueError("Server-generated XML is only allowed in private buckets")
        return
    if not tipo_guardable(content_type, path):
        raise ValueError("Refusing to store an executable/markup file type in Storage")


def public_object_url(bucket: str, path: str) -> str:
    settings.require_supabase_public()
    bucket, encoded_path = _encoded_object(bucket, path)
    return f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{encoded_path}"


def object_path_from_url(bucket: str, url: str | None) -> str | None:
    """Object path inside ``bucket`` for a stored public/signed Storage URL (or None)."""
    if not isinstance(url, str):
        return None
    bucket = _require_bucket(bucket)
    m = re.search(r"/storage/v1/object/(?:public|sign|authenticated)/" + re.escape(bucket) + r"/([^?#]+)", url)
    if not m:
        return None
    try:
        return _normalize_object_path(unquote(m.group(1)))
    except ValueError:
        return None


async def upload_object(
    bucket: str,
    path: str,
    content: bytes,
    *,
    content_type: str,
    timeout: float = 60,
    server_generated_xml: bool = False,
) -> str:
    """Upload an object using service-role credentials and return its public URL.

    For buckets in ``PRIVATE_BUCKETS`` the returned URL is only an identifier:
    reading requires ``create_signed_object_url``.
    """
    settings.require_supabase_service()
    ensure_storable(path, content_type, bucket=bucket, server_generated_xml=server_generated_xml)
    bucket, encoded_path = _encoded_object(bucket, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/{bucket}/{encoded_path}",
            headers=_service_headers(content_type=content_type, upsert=True,
                                     cache_control=cache_control_for(bucket)),
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
    download: str | bool | None = None,
) -> str:
    """Create a short-lived signed URL for a private object.

    ``download`` forces ``Content-Disposition: attachment`` (``True`` keeps the
    stored name, a string sets the suggested file name). Use it for anything
    that should not be opened inline by the browser.
    """
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
    if not (signed.startswith("http://") or signed.startswith("https://")):
        if not signed.startswith("/"):
            signed = "/" + signed
        signed = f"{settings.supabase_url}/storage/v1{signed}"
    if download:
        nombre = "" if download is True else quote(str(download), safe="")
        signed += ("&" if "?" in signed else "?") + f"download={nombre}"
    return signed


async def create_signed_object_urls(
    bucket: str,
    paths: list[str] | tuple[str, ...],
    *,
    expires_in: int,
    timeout: float = 15,
    download_for: frozenset[str] | set[str] = frozenset(),
) -> dict[str, str]:
    """Sign several private objects in one request. Returns {path: signed_url}.

    Paths that Supabase cannot sign are left out. ``download_for`` lists the
    paths that must be served as attachments (not opened inline).
    """
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise ValueError("Signed URL expiration must be a positive integer")
    settings.require_supabase_service()
    bucket = _require_bucket(bucket)
    normalized = list(dict.fromkeys(_normalize_object_path(p) for p in paths if p))
    if not normalized:
        return {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/sign/{bucket}",
            headers=_service_headers(content_type="application/json"),
            json={"expiresIn": expires_in, "paths": normalized},
        )
    response.raise_for_status()
    result: dict[str, str] = {}
    for item in response.json() or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        path, signed = item.get("path"), item.get("signedURL")
        if not isinstance(path, str) or not isinstance(signed, str) or not signed:
            continue
        if not (signed.startswith("http://") or signed.startswith("https://")):
            signed = f"{settings.supabase_url}/storage/v1" + (signed if signed.startswith("/") else "/" + signed)
        if path in download_for:
            signed += ("&" if "?" in signed else "?") + "download="
        result[path] = signed
    return result


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


async def list_buckets(*, timeout: float = 20) -> list[dict]:
    """Read-only: every bucket with its ``public`` flag (service role)."""
    settings.require_supabase_service()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{settings.supabase_url}/storage/v1/bucket", headers=_service_headers())
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


async def list_objects(
    bucket: str,
    prefix: str = "",
    *,
    limit: int = 1000,
    offset: int = 0,
    timeout: float = 30,
) -> list[dict]:
    """Read-only: one page of names/metadata under ``prefix``. Never downloads content.

    Folders come back with ``id`` = None; files carry ``metadata`` (mimetype, size).
    """
    settings.require_supabase_service()
    bucket = _require_bucket(bucket)
    prefix = prefix.strip("/")
    if prefix and any(part in ("", ".", "..") for part in prefix.split("/")):
        raise ValueError("Storage prefix contains an invalid segment")
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.supabase_url}/storage/v1/object/list/{bucket}",
            headers=_service_headers(content_type="application/json"),
            json={"prefix": prefix, "limit": limit, "offset": offset,
                  "sortBy": {"column": "name", "order": "asc"}},
        )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []
