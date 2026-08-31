"""Shared EasyBroker compatibility infrastructure.

Preserves main.py's historical global API-key fallback and bounded retry policy
while domain routes are progressively extracted. Organization-scoped user keys
remain the preferred runtime path.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from core.config import settings


EB_BASE = "https://api.easybroker.com/v1"
_CONFIG_FILE = Path(__file__).resolve().parents[1] / "config.json"

# EasyBroker limita su API a 20 peticiones por segundo. Estos valores preserve
# el ritmo histórico de import-all exactamente.
_EB_LOTE = 8
_EB_PAUSA_LOTE = 0.5
_EB_REINTENTOS = 5
_EB_ESPERA_BASE = 1.5
_EB_ESPERA_MAX = 20.0


def _load_legacy_config() -> dict:
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


EB_API_KEY = settings.easybroker_api_key or _load_legacy_config().get("eb_api_key", "")


def eb_headers(key: str | None = None) -> dict[str, str]:
    k = key or EB_API_KEY
    return {"X-Authorization": k, "accept": "application/json"}


def extract_colonia(location_str: str) -> str:
    """Extract colonia from the historical 'Colonia, Ciudad, Estado' shape."""
    if not location_str:
        return ""
    parts = [p.strip() for p in location_str.split(",")]
    return parts[0] if parts else location_str.strip()


def normalize(s: str) -> str:
    """Preserve the legacy lightweight accent normalization used by EB/AVM."""
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")]:
        s = s.lower().replace(a, b)
    return s


async def _eb_get_reintentos(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    params: dict | None = None,
    timeout: float = 20.0,
):
    """GET EasyBroker preserving the historical 429/5xx backoff contract."""
    ultimo = None
    for intento in range(_EB_REINTENTOS):
        try:
            r = await client.get(url, headers=headers, params=params, timeout=timeout)
            ultimo = r
            if r.status_code == 429 or r.status_code >= 500:
                try:
                    espera = float(r.headers.get("Retry-After") or 0)
                except (TypeError, ValueError):
                    espera = 0.0
                if espera <= 0:
                    espera = _EB_ESPERA_BASE * (2 ** intento)
                await asyncio.sleep(min(espera, _EB_ESPERA_MAX))
                continue
            return r
        except Exception:
            ultimo = None
            await asyncio.sleep(min(_EB_ESPERA_BASE * (2 ** intento), _EB_ESPERA_MAX))
    return ultimo
