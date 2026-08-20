"""Safe outbound HTTP primitives for user-supplied public URLs.

Any backend feature that downloads a URL supplied by a user must use this layer
rather than calling ``httpx.get`` directly. It blocks local/private targets,
validates every redirect, and limits response size.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx


class UnsafePublicURL(ValueError):
    """Raised when a URL could reach a non-public network destination."""


@dataclass(frozen=True)
class PublicHTTPResult:
    """Bounded public HTTP response without implicit status-code raising."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        """Decode content with httpx's response-text semantics."""
        return httpx.Response(
            self.status_code,
            headers=self.headers,
            content=self.content,
        ).text


_REDIRECTS = {301, 302, 303, 307, 308}


def _parsed_url(url: str):
    if not isinstance(url, str) or not url.strip():
        raise UnsafePublicURL("URL is required")
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafePublicURL("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise UnsafePublicURL("URL hostname is required")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafePublicURL("Credentials in URLs are not allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafePublicURL("Local hostnames are not allowed")
    return parsed


def _require_global_ip(value: str) -> None:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise UnsafePublicURL("Private, local, reserved, or loopback addresses are not allowed")


async def assert_public_http_url(url: str) -> None:
    """Resolve a URL and require every destination address to be globally routable."""
    parsed = _parsed_url(url)
    host = parsed.hostname
    if host is None:
        raise UnsafePublicURL("URL hostname is required")

    try:
        _require_global_ip(host)
        return
    except ValueError:
        pass

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise UnsafePublicURL("URL hostname could not be resolved") from exc

    addresses = {info[4][0] for info in infos if info and info[4]}
    if not addresses:
        raise UnsafePublicURL("URL hostname did not resolve to an address")
    for address in addresses:
        _require_global_ip(address)


async def fetch_public_http_result(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 20 * 1024 * 1024,
    max_redirects: int = 3,
    headers: dict[str, str] | None = None,
) -> PublicHTTPResult:
    """Fetch bounded public HTTP(S) content while preserving the final status.

    Unlike :func:`fetch_public_bytes`, non-2xx final responses are returned to
    the caller instead of raising. This is useful for domain logic that needs
    to distinguish statuses such as 403/429/5xx while still enforcing the same
    SSRF, redirect, and response-size protections.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_redirects < 0:
        raise ValueError("max_redirects must not be negative")

    current = url
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for redirect_count in range(max_redirects + 1):
            await assert_public_http_url(current)
            async with client.stream("GET", current) as response:
                if response.status_code in _REDIRECTS:
                    if redirect_count >= max_redirects:
                        raise UnsafePublicURL("Too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafePublicURL("Redirect is missing Location header")
                    current = urljoin(current, location)
                    continue

                declared = response.headers.get("content-length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError):
                        declared_size = None
                    if declared_size is not None and declared_size > max_bytes:
                        raise ValueError("Remote response exceeds size limit")

                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise ValueError("Remote response exceeds size limit")

                return PublicHTTPResult(
                    status_code=response.status_code,
                    headers={str(k).lower(): str(v) for k, v in response.headers.items()},
                    content=bytes(chunks),
                    url=current,
                )

    raise UnsafePublicURL("Unable to fetch public URL")


async def fetch_public_bytes(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 20 * 1024 * 1024,
    max_redirects: int = 3,
) -> bytes:
    """Download bounded bytes from a public HTTP(S) URL with SSRF defenses."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_redirects < 0:
        raise ValueError("max_redirects must not be negative")

    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for redirect_count in range(max_redirects + 1):
            await assert_public_http_url(current)
            async with client.stream("GET", current) as response:
                if response.status_code in _REDIRECTS:
                    if redirect_count >= max_redirects:
                        raise UnsafePublicURL("Too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafePublicURL("Redirect is missing Location header")
                    current = urljoin(current, location)
                    continue

                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > max_bytes:
                            raise ValueError("Remote response exceeds size limit")
                    except ValueError as exc:
                        if str(exc) == "Remote response exceeds size limit":
                            raise

                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise ValueError("Remote response exceeds size limit")
                return bytes(chunks)

    raise UnsafePublicURL("Unable to fetch public URL")
