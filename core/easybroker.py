"""Shared EasyBroker compatibility infrastructure.

Preserves main.py's historical global API-key fallback while domain routes are
progressively extracted. Organization-scoped user keys remain the preferred
runtime path; this module only centralizes the legacy base URL/header helper.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.config import settings


EB_BASE = "https://api.easybroker.com/v1"
_CONFIG_FILE = Path(__file__).resolve().parents[1] / "config.json"


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
