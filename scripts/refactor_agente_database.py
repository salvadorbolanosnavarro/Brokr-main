#!/usr/bin/env python3
"""Route Agente's Supabase data access through core.database without changing tool logic."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "agente.py"

OLD_IMPORT = '''from core.auth import get_user_id_from_token
from core.config import settings
'''
NEW_IMPORT = '''from core.auth import get_user_id_from_token
from core.config import settings
from core.database import get_rows, patch_rows, post_rows
'''

OLD_CONFIG = '''SUPABASE_URL         = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key
'''
NEW_CONFIG = '''SUPABASE_URL         = settings.supabase_url
'''

OLD_HEADERS = '''def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


'''
NEW_ADAPTER = '''class _CoreDbResponse:
    """Small response facade preserving the existing agent tool contract."""

    def __init__(self, status_code: int, data=None, text: str = ""):
        self.status_code = status_code
        self._data = data if data is not None else []
        self.text = text

    def json(self):
        return self._data


class _CoreDbClient:
    """Compatibility adapter: response semantics stay local, I/O lives in Core."""

    def __init__(self, timeout: float = 15):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @staticmethod
    def _table(url: str) -> str:
        marker = "/rest/v1/"
        if marker not in url:
            raise ValueError("Agente DB adapter received a non-Supabase URL")
        return url.split(marker, 1)[1].split("?", 1)[0].strip("/")

    @staticmethod
    def _error(exc: Exception) -> _CoreDbResponse:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            return _CoreDbResponse(response.status_code, [], response.text)
        return _CoreDbResponse(503, [], str(exc))

    async def get(self, url: str, *, headers=None, params=None):
        try:
            rows = await get_rows(self._table(url), params or {}, timeout=self.timeout)
            return _CoreDbResponse(200, rows)
        except Exception as exc:
            return self._error(exc)

    async def post(self, url: str, *, headers=None, json=None):
        prefer = (headers or {}).get("Prefer", "return=minimal")
        try:
            rows = await post_rows(
                self._table(url),
                json,
                prefer=prefer,
                timeout=self.timeout,
            )
            return _CoreDbResponse(201, rows)
        except Exception as exc:
            return self._error(exc)

    async def patch(self, url: str, *, headers=None, params=None, json=None):
        prefer = (headers or {}).get("Prefer", "return=minimal")
        try:
            rows = await patch_rows(
                self._table(url),
                params or {},
                json or {},
                prefer=prefer,
                timeout=self.timeout,
            )
            return _CoreDbResponse(204 if not rows else 200, rows)
        except Exception as exc:
            return self._error(exc)


'''

OLD_HEALTH = '        "supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),\n'
NEW_HEALTH = '        "supabase": bool(settings.supabase_url and settings.supabase_service_key),\n'


def transform(text: str) -> str:
    if "from core.database import get_rows, patch_rows, post_rows" in text:
        raise RuntimeError("Agente database refactor already appears applied")
    if text.count(OLD_IMPORT) != 1:
        raise RuntimeError("Agente Core import block does not match reviewed source")
    if text.count(OLD_CONFIG) != 1:
        raise RuntimeError("Agente Supabase config aliases do not match reviewed source")
    if text.count(OLD_HEADERS) != 1:
        raise RuntimeError("Agente service header helper does not match reviewed source")
    if text.count(OLD_HEALTH) != 1:
        raise RuntimeError("Agente health Supabase check does not match reviewed source")

    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)
    text = text.replace(OLD_CONFIG, NEW_CONFIG, 1)
    text = text.replace(OLD_HEADERS, NEW_ADAPTER, 1)
    text = text.replace(
        "async with httpx.AsyncClient(timeout=15) as client:",
        "async with _CoreDbClient(timeout=15) as client:",
    )
    text = text.replace("headers=_sb_headers()", "headers={}")
    text = text.replace("h = _sb_headers(); h[\"Prefer\"] = \"return=representation\"", 'h = {"Prefer": "return=representation"}')
    text = text.replace(OLD_HEALTH, NEW_HEALTH, 1)
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "routers/agente.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
