#!/usr/bin/env python3
"""Apply the one-time Organizaciones infrastructure migration to shared Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "organizaciones.py"

OLD_IMPORTS = '''import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
'''

NEW_IMPORTS = '''import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.permissions import ROLE_AGENT, VALID_ORG_ROLES, VALID_PERMISSIONS, default_permission
'''

INFRA_START = "# ── Config (mismas env vars que main.py) ──────────────────────────────────\n"
INFRA_END = "# ══════════════════════════════════════════════════════════════════════════\n# HELPERS PÚBLICOS — main.py y agente.py importan de aquí\n# ══════════════════════════════════════════════════════════════════════════\n"

NEW_INFRA = '''# ── Infraestructura compartida ────────────────────────────────────────────
# Keep the router's historical helper contracts while Core owns environment
# names, privileged credentials and Supabase HTTP construction.
APP_URL = settings.app_url
PERMISOS_VALIDOS = set(VALID_PERMISSIONS)
ROLES_ORG_VALIDOS = set(VALID_ORG_ROLES)
DEFAULTS_AGENTE = {permission: default_permission(ROLE_AGENT, permission) for permission in VALID_PERMISSIONS}


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    # Legacy contract: reads return [] on Supabase/configuration failure.
    try:
        return await get_rows(tabla, params, timeout=10)
    except Exception:
        return []


async def _sb_post(tabla: str, payload, prefer="return=representation") -> Optional[list]:
    try:
        rows = await post_rows(tabla, payload, prefer=prefer, timeout=10)
        return rows or None
    except httpx.HTTPStatusError as exc:
        response = exc.response
        raise HTTPException(
            status_code=500,
            detail=f"Supabase {response.status_code}: {response.text[:200]}",
        ) from exc


async def _sb_patch(tabla: str, params: dict, payload: dict) -> None:
    try:
        await patch_rows(tabla, params, payload, prefer="return=minimal", timeout=10)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        raise HTTPException(
            status_code=500,
            detail=f"Supabase {response.status_code}: {response.text[:200]}",
        ) from exc


async def _sb_delete(tabla: str, params: dict) -> None:
    try:
        await delete_rows(tabla, params, timeout=10)
    except httpx.HTTPStatusError:
        # Preserve the historical delete helper contract, which ignored
        # non-success response statuses.
        return None


'''

AUTH_START = 'async def get_user_id_from_token(request: Request) -> Optional[str]:\n'
AUTH_END = 'async def get_org_context(user_id: str) -> Optional[Dict[str, Any]]:\n'


def transform(text: str) -> str:
    if "from core.auth import get_user_id_from_token" in text:
        raise RuntimeError("Organizaciones Core infrastructure refactor already appears applied")
    if text.count(OLD_IMPORTS) != 1:
        raise RuntimeError("Organizaciones import block does not match reviewed source")
    if text.count(INFRA_START) != 1 or text.count(INFRA_END) != 1:
        raise RuntimeError("Organizaciones infrastructure block does not match reviewed source")
    if text.count(AUTH_START) != 1 or text.count(AUTH_END) != 1:
        raise RuntimeError("Organizaciones auth block does not match reviewed source")

    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)

    start = text.index(INFRA_START)
    end = text.index(INFRA_END, start)
    text = text[:start] + NEW_INFRA + text[end:]

    start = text.index(AUTH_START)
    end = text.index(AUTH_END, start)
    text = text[:start] + text[end:]
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(ROOT)} to canonical Core infrastructure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
