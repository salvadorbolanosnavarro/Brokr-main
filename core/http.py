"""Safe outbound HTTP primitives for user-supplied public URLs."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


class UnsafePublicURL(ValueError):
    """Raised when a URL could reach a non-public network destination."""


@dataclass(frozen=True)
class PublicHTTPResult:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str

    @property
    def text(self) -> str:
        return httpx.Response(self.status_code, headers=self.headers, content=self.content).text


@dataclass(frozen=True)
class _ResolvedPublicURL:
    original_url: str
    request_url: str
    host_header: str
    sni_hostname: str


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


def _require_global_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise UnsafePublicURL("Private, local, reserved, or loopback addresses are not allowed")
    return address


async def _resolve_public_http_url(url: str) -> _ResolvedPublicURL:
    parsed = _parsed_url(url)
    host = parsed.hostname
    if host is None:
        raise UnsafePublicURL("URL hostname is required")

    # Distinguish "not an IP literal" from "an unsafe IP literal". UnsafePublicURL
    # is a ValueError subclass, so catching ValueError around _require_global_ip()
    # would incorrectly swallow our own rejection.
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if literal_ip is not None:
        if not literal_ip.is_global:
            raise UnsafePublicURL("Private, local, reserved, or loopback addresses are not allowed")
        chosen = literal_ip
    else:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise UnsafePublicURL("URL hostname could not be resolved") from exc
        ordered: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        seen: set[str] = set()
        for info in infos:
            if not info or not info[4]:
                continue
            raw = info[4][0]
            if raw in seen:
                continue
            seen.add(raw)
            ordered.append(_require_global_ip(raw))
        if not ordered:
            raise UnsafePublicURL("URL hostname did not resolve to an address")
        # Pin the actual request to one address from the validated resolution.
        # This prevents httpx from performing a second DNS lookup that could be
        # rebound to a private address after validation.
        chosen = ordered[0]

    default_port = 443 if parsed.scheme == "https" else 80
    host_header = host if port == default_port else f"{host}:{port}"
    ip_text = str(chosen)
    netloc_host = f"[{ip_text}]" if chosen.version == 6 else ip_text
    netloc = netloc_host if port == default_port else f"{netloc_host}:{port}"
    request_url = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    return _ResolvedPublicURL(
        original_url=url,
        request_url=request_url,
        host_header=host_header,
        sni_hostname=host,
    )


async def assert_public_http_url(url: str) -> None:
    await _resolve_public_http_url(url)


async def fetch_public_http_result(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 20 * 1024 * 1024,
    max_redirects: int = 3,
    headers: dict[str, str] | None = None,
) -> PublicHTTPResult:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_redirects < 0:
        raise ValueError("max_redirects must not be negative")
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for redirect_count in range(max_redirects + 1):
            resolved = await _resolve_public_http_url(current)
            request_headers = dict(headers or {})
            request_headers["Host"] = resolved.host_header
            request = client.build_request("GET", resolved.request_url, headers=request_headers)
            # httpcore honors this extension for TLS SNI/certificate hostname while
            # the TCP connection remains pinned to the validated IP literal.
            request.extensions["sni_hostname"] = resolved.sni_hostname.encode("ascii")
            response = await client.send(request, stream=True, follow_redirects=False)
            try:
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
            finally:
                await response.aclose()
    raise UnsafePublicURL("Unable to fetch public URL")


async def fetch_public_bytes(
    url: str,
    *,
    timeout: float = 30,
    max_bytes: int = 20 * 1024 * 1024,
    max_redirects: int = 3,
) -> bytes:
    result = await fetch_public_http_result(
        url,
        timeout=timeout,
        max_bytes=max_bytes,
        max_redirects=max_redirects,
    )
    if result.status_code >= 400:
        response = httpx.Response(result.status_code, headers=result.headers, content=result.content)
        response.raise_for_status()
    return result.content
