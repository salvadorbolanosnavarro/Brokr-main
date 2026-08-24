"""Shared Meta Graph API transport and legacy-compatible error handling."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging

import httpx
from fastapi import HTTPException

from core.config import settings
from core.legacy_main_config import legacy_main_settings


_log = logging.getLogger("broquer.facebook")
_FB_APP_SECRET = settings.legacy_main_fb_app_secret

FB_API_VERSION = legacy_main_settings.fb_api_version
FB_GRAPH = f"https://graph.facebook.com/{FB_API_VERSION}"

_FB_REINTENTOS = 4
_FB_ESPERA_BASE = 1.5
_FB_ESPERA_MAX = 30.0
_FB_CODIGOS_REINTENTABLES = {
    1, 2, 4, 17, 32, 341, 613,
    80000, 80001, 80002, 80003, 80004, 80005, 80006,
}
_FB_CODIGOS_TOKEN = {102, 190, 463, 467}
_FB_USAR_PROOF = legacy_main_settings.fb_appsecret_proof

_FB_ERRORES_COMUNES = {
    1487888: "Tu cuenta publicitaria requiere un Píxel de Facebook configurado para optimizar conversiones. Contacta soporte de Broquer.",
    4834011: "La cuenta tiene 'Optimización del presupuesto de campaña' activada. Desactívala en Business Manager o crea el anuncio directamente en Ads Manager.",
    2069013: "La imagen no cumple los requisitos de Facebook (mínimo 600x600, sin texto excesivo). Usa otra imagen.",
    1815245: "Para anuncios inmobiliarios en EE.UU./Canadá, Meta exige la categoría especial 'Vivienda'. En México no aplica — verifica tu ubicación de cuenta.",
    1815111: "El público objetivo es muy pequeño. Amplía la edad, la ciudad o quita filtros.",
    368: "Facebook bloqueó la acción por seguridad. Espera unos minutos y reintenta, o reconecta tu cuenta.",
    190: "Tu sesión de Facebook expiró o fue revocada. Reconecta tu Facebook desde tu perfil.",
    102: "Tu sesión de Facebook expiró. Reconecta tu Facebook desde tu perfil.",
    4: "Facebook está limitando las peticiones de Broquer en este momento. Espera unos minutos y reintenta.",
    17: "Facebook está limitando las peticiones de tu cuenta. Espera unos minutos y reintenta.",
    613: "Alcanzaste el límite de peticiones de Facebook. Espera unos minutos y reintenta.",
    80004: "Alcanzaste el límite de peticiones de la API de anuncios. Espera unos minutos y reintenta.",
}


def _fb_appsecret_proof(token: str) -> str:
    if not token or not _FB_APP_SECRET:
        return ""
    try:
        return hmac.new(
            _FB_APP_SECRET.encode("utf-8"),
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    except Exception:
        return ""


def _fb_parse_error(resp: "httpx.Response | None") -> dict:
    if resp is None:
        return {"message": "Facebook no respondió.", "code": None, "error_subcode": None}
    try:
        payload = resp.json()
    except Exception:
        return {"message": (resp.text or "")[:300], "code": None, "error_subcode": None}
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return payload["error"]
    return {}


def _fb_friendly_error(resp_text: str, prefix: str) -> str:
    try:
        payload = json.loads(resp_text or "{}")
        err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
        sub = err.get("error_subcode") or err.get("code")
        user_title = err.get("error_user_title") or ""
        user_msg = err.get("error_user_msg") or err.get("message") or ""
        if sub in _FB_ERRORES_COMUNES:
            return f"{prefix}: {_FB_ERRORES_COMUNES[sub]}"
        if user_title or user_msg:
            return f"{prefix}: {user_title}. {user_msg}".strip(". ").strip()
        return f"{prefix}: {err.get('message') or (resp_text or '')[:300]}"
    except Exception:
        return f"{prefix}: {(resp_text or '')[:300]}"


def _fb_espera_por_uso(headers) -> float:
    raw = ""
    try:
        raw = headers.get("X-Business-Use-Case-Usage") or headers.get("x-business-use-case-usage") or ""
    except Exception:
        return 0.0
    if not raw:
        return 0.0
    try:
        data = json.loads(raw)
    except Exception:
        return 0.0
    peor_uso = 0
    bloqueado = False
    for entradas in (data or {}).values():
        for e in (entradas or []):
            if not isinstance(e, dict):
                continue
            for k in ("call_count", "total_cputime", "total_time"):
                try:
                    peor_uso = max(peor_uso, int(e.get(k) or 0))
                except (TypeError, ValueError):
                    pass
            try:
                if float(e.get("estimated_time_to_regain_access") or 0) > 0:
                    bloqueado = True
            except (TypeError, ValueError):
                pass
    if bloqueado:
        return _FB_ESPERA_MAX
    if peor_uso >= 95:
        return 5.0
    if peor_uso >= 80:
        return 1.0
    return 0.0


def _fb_debe_reintentar(resp: "httpx.Response") -> bool:
    if resp.status_code == 429 or resp.status_code >= 500:
        return True
    if resp.status_code == 400 or resp.status_code == 403:
        err = _fb_parse_error(resp)
        code = err.get("code")
        if code in _FB_CODIGOS_TOKEN:
            return False
        try:
            return int(code) in _FB_CODIGOS_REINTENTABLES
        except (TypeError, ValueError):
            return False
    return False


async def _fb_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: str = "",
    params: dict = None,
    json_body: dict = None,
    data: dict = None,
    files=None,
    timeout: float = 30.0,
    reintentos: int = _FB_REINTENTOS,
    espera_base: float = None,
    espera_max: float = None,
) -> "httpx.Response":
    url = path if path.startswith("http") else f"{FB_GRAPH}/{path.lstrip('/')}"
    base = _FB_ESPERA_BASE if espera_base is None else espera_base
    techo = _FB_ESPERA_MAX if espera_max is None else espera_max
    p = dict(params or {})
    if token:
        p.setdefault("access_token", token)
    proof = _fb_appsecret_proof(p.get("access_token", ""))
    if proof and _FB_USAR_PROOF:
        p.setdefault("appsecret_proof", proof)

    ultimo = None
    for intento in range(max(1, reintentos)):
        try:
            r = await client.request(
                method.upper(),
                url,
                params=p,
                json=json_body,
                data=data,
                files=files,
                timeout=timeout,
            )
            ultimo = r
            if (
                r.status_code in (400, 403)
                and "appsecret_proof" in p
                and "appsecret_proof" in (r.text or "")
            ):
                _log.warning("appsecret_proof rechazado por Meta; reintento sin él")
                p.pop("appsecret_proof", None)
                continue

            if not _fb_debe_reintentar(r) or intento == reintentos - 1:
                return r

            try:
                espera = float(r.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                espera = 0.0
            espera = max(espera, _fb_espera_por_uso(r.headers))
            if espera <= 0:
                espera = base * (2 ** intento)
            espera = min(espera, techo)
            _log.warning(
                "Meta %s %s → %s; reintento %s/%s en %.1fs",
                method.upper(),
                url.split("?")[0],
                r.status_code,
                intento + 1,
                reintentos,
                espera,
            )
            await asyncio.sleep(espera)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            _log.warning(
                "Fallo de red hablando con Meta (%s); intento %s/%s: %s",
                url.split("?")[0],
                intento + 1,
                reintentos,
                e,
            )
            ultimo = None
            if intento == reintentos - 1:
                break
            await asyncio.sleep(min(base * (2 ** intento), techo))
    return ultimo


def _fb_exigir_ok(
    resp: "httpx.Response | None",
    prefix: str,
    status_code: int = 502,
) -> dict:
    if resp is None:
        raise HTTPException(
            status_code=504,
            detail=f"{prefix}: Facebook no respondió después de varios intentos.",
        )
    if resp.status_code not in (200, 201, 204):
        err = _fb_parse_error(resp)
        code = err.get("code")
        sc = 401 if code in _FB_CODIGOS_TOKEN else status_code
        raise HTTPException(status_code=sc, detail=_fb_friendly_error(resp.text, prefix))
    try:
        return resp.json() or {}
    except Exception:
        return {}


async def _fb_get_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    token: str,
    params: dict = None,
    prefix: str = "Error de Facebook",
    timeout: float = 30.0,
) -> dict:
    r = await _fb_request(client, "GET", path, token=token, params=params, timeout=timeout)
    return _fb_exigir_ok(r, prefix)


async def _fb_paginate(
    client: httpx.AsyncClient,
    path: str,
    *,
    token: str,
    params: dict = None,
    max_paginas: int = 10,
    max_items: int = 500,
    prefix: str = "Error de Facebook",
    timeout: float = 30.0,
    espera_base: float = None,
    espera_max: float = None,
) -> list:
    items: list = []
    afinado = {"espera_base": espera_base, "espera_max": espera_max}
    r = await _fb_request(
        client,
        "GET",
        path,
        token=token,
        params=params,
        timeout=timeout,
        **afinado,
    )
    data = _fb_exigir_ok(r, prefix)
    items.extend(data.get("data") or [])
    paginas = 1
    while paginas < max_paginas and len(items) < max_items:
        siguiente = ((data.get("paging") or {}).get("next")) or ""
        if not siguiente:
            break
        r = await _fb_request(client, "GET", siguiente, timeout=timeout, **afinado)
        if r is None or r.status_code != 200:
            break
        try:
            data = r.json() or {}
        except Exception:
            break
        nuevos = data.get("data") or []
        if not nuevos:
            break
        items.extend(nuevos)
        paginas += 1
    return items[:max_items]
