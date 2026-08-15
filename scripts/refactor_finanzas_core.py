#!/usr/bin/env python3
"""Apply the first Finanzas migration cut: config, auth and database to Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "finanzas.py"

OLD_IMPORTS = '''import os
import io
import csv
import json
import base64
import logging
import uuid as _uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
'''

NEW_IMPORTS = '''import os
import io
import csv
import json
import base64
import logging
import uuid as _uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers
'''

CONFIG_START = "# ── Config (mismas env vars que main.py) ──────────────────────────────────\n"
CONFIG_END = '\nBUCKET = "fin-comprobantes"\n'
NEW_CONFIG = '''# ── Config ────────────────────────────────────────────────────────────────
# Environment names and privileged credential policy live only in Core.
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
'''

INFRA_START = "# ══════════════════════════════════════════════════════════════════════════\n# ACCESO A SUPABASE (service key — se brinca RLS, por eso validamos antes)\n# ══════════════════════════════════════════════════════════════════════════\n"
INFRA_END = "# ══════════════════════════════════════════════════════════════════════════\n# HELPERS DE FECHAS Y VALIDACIÓN\n# ══════════════════════════════════════════════════════════════════════════\n"
NEW_INFRA = '''# ══════════════════════════════════════════════════════════════════════════
# ACCESO A SUPABASE — compatibilidad sobre Core
# ══════════════════════════════════════════════════════════════════════════

def _headers(prefer: Optional[str] = None) -> Dict[str, str]:
    # Temporary compatibility adapter for the Storage code below. Database
    # operations themselves use core.database directly.
    return service_headers(prefer=prefer)


async def _sb_get(tabla: str, params: dict) -> List[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("GET %s -> %s %s", tabla, response.status_code, response.text[:180])
        return []
    except RuntimeError:
        # Preserve the historical read contract while still denying privileged
        # access when service-role configuration is absent.
        return []


async def _sb_post(tabla: str, payload, prefer: str = "return=representation") -> List[dict]:
    try:
        return await post_rows(tabla, payload, prefer=prefer, timeout=20)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("POST %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo guardar. Intenta de nuevo.") from exc


async def _sb_patch(tabla: str, params: dict, payload: dict) -> List[dict]:
    try:
        return await patch_rows(
            tabla,
            params,
            payload,
            prefer="return=representation",
            timeout=20,
        )
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("PATCH %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo actualizar. Intenta de nuevo.") from exc


async def _sb_delete(tabla: str, params: dict) -> None:
    try:
        await delete_rows(tabla, params, timeout=20)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("DELETE %s -> %s %s", tabla, response.status_code, response.text[:180])
        raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.") from exc
    except RuntimeError as exc:
        raise HTTPException(500, "No se pudo borrar. Intenta de nuevo.") from exc


async def _uid(request: Request) -> str:
    return await require_user_id(request, detail="Inicia sesión para continuar.")


'''


def transform(text: str) -> str:
    if "from core.auth import require_user_id" in text:
        raise RuntimeError("Finanzas Core refactor already appears applied")
    if text.count(OLD_IMPORTS) != 1:
        raise RuntimeError("Finanzas import block does not match reviewed source")
    if text.count(CONFIG_START) != 1 or text.count(CONFIG_END) != 1:
        raise RuntimeError("Finanzas config block does not match reviewed source")
    if text.count(INFRA_START) != 1 or text.count(INFRA_END) != 1:
        raise RuntimeError("Finanzas Supabase/auth block does not match reviewed source")

    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)
    start = text.index(CONFIG_START)
    end = text.index(CONFIG_END, start)
    text = text[:start] + NEW_CONFIG + text[end:]

    start = text.index(INFRA_START)
    end = text.index(INFRA_END, start)
    text = text[:start] + NEW_INFRA + text[end:]
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    compile(updated, "routers/finanzas.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
