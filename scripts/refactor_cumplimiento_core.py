#!/usr/bin/env python3
"""Migrate Cumplimiento shared infrastructure without changing PLD rules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "cumplimiento.py"

OLD_IMPORTS = '''import os
import re
import json
import secrets
import logging
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
'''
NEW_IMPORTS = '''import re
import json
import secrets
import logging
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import get_rows, patch_rows, post_rows
from core.storage import create_signed_object_url, upload_object
'''

CONFIG_START = "# ── Config (mismas env vars que main.py) ──────────────────────────────────\n"
CONFIG_END = '\nBUCKET = "pld-expedientes"\n'
NEW_CONFIG = '''# ── Config ────────────────────────────────────────────────────────────────
# Environment names and privileged credential policy live only in Core.
APP_URL = settings.app_url
'''

INFRA_START = "# ══════════════════════════════════════════════════════════════════════════\n# ACCESO A SUPABASE (service key — se brinca RLS, por eso validamos antes)\n# ══════════════════════════════════════════════════════════════════════════\n"
INFRA_END = "# ══════════════════════════════════════════════════════════════════════════\n# BITÁCORA — la evidencia. Se escribe, nunca se corrige.\n# ══════════════════════════════════════════════════════════════════════════\n"
NEW_INFRA = '''# ══════════════════════════════════════════════════════════════════════════
# ACCESO A SUPABASE — compatibilidad sobre Core
# ══════════════════════════════════════════════════════════════════════════

async def _sb_get(tabla: str, params: dict) -> List[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.warning("GET %s -> %s %s", tabla, response.status_code, response.text[:180])
        return []
    except RuntimeError:
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


async def _uid(request: Request) -> str:
    return await require_user_id(request, detail="Inicia sesión para continuar.")


'''

OLD_DOC_UPLOAD = '''    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": mime, "x-upsert": "true"},
            content=contenido)
        if r.status_code not in (200, 201):
            log.warning("upload -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.")
'''
NEW_DOC_UPLOAD = '''    try:
        await upload_object(
            BUCKET,
            ruta,
            contenido,
            content_type=mime,
            timeout=60,
        )
    except Exception as exc:
        log.warning("upload PLD falló: %s", exc)
        raise HTTPException(500, "No se pudo guardar el archivo. Intenta de nuevo.") from exc
'''

OLD_SIGN = '''    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{ruta}",
                         headers=_headers(), json={"expiresIn": FIRMA_SEGUNDOS})
        if r.status_code != 200:
            log.warning("sign -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "No se pudo abrir el documento.")
        firmada = r.json().get("signedURL", "")

    await bitacora(uid, "documento_consultado",
'''
NEW_SIGN = '''    try:
        firmada = await create_signed_object_url(
            BUCKET,
            ruta,
            expires_in=FIRMA_SEGUNDOS,
            timeout=15,
        )
    except Exception as exc:
        log.warning("sign PLD falló: %s", exc)
        raise HTTPException(500, "No se pudo abrir el documento.") from exc

    await bitacora(uid, "documento_consultado",
'''
OLD_SIGN_RETURN = '    return {"url": f"{SUPABASE_URL}/storage/v1{firmada}", "expira_segundos": FIRMA_SEGUNDOS}\n'
NEW_SIGN_RETURN = '    return {"url": firmada, "expira_segundos": FIRMA_SEGUNDOS}\n'

OLD_XML_UPLOAD = '''    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}",
                         headers={"apikey": SUPABASE_SERVICE_KEY,
                                  "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                  "Content-Type": "application/xml", "x-upsert": "true"},
                         content=xml.encode("utf-8"))
        if r.status_code not in (200, 201):
            log.warning("upload xml -> %s %s", r.status_code, r.text[:200])
            raise HTTPException(500, "Se armó el aviso pero no se pudo guardar el archivo.")
'''
NEW_XML_UPLOAD = '''    try:
        await upload_object(
            BUCKET,
            ruta,
            xml.encode("utf-8"),
            content_type="application/xml",
            timeout=30,
        )
    except Exception as exc:
        log.warning("upload XML PLD falló: %s", exc)
        raise HTTPException(500, "Se armó el aviso pero no se pudo guardar el archivo.") from exc
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Cumplimiento {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.auth import require_user_id" in text:
        raise RuntimeError("Cumplimiento Core refactor already appears applied")
    text = _replace_once(text, OLD_IMPORTS, NEW_IMPORTS, "imports")

    if text.count(CONFIG_START) != 1 or text.count(CONFIG_END) != 1:
        raise RuntimeError("Cumplimiento config block does not match reviewed source")
    start = text.index(CONFIG_START)
    end = text.index(CONFIG_END, start)
    text = text[:start] + NEW_CONFIG + text[end:]

    if text.count(INFRA_START) != 1 or text.count(INFRA_END) != 1:
        raise RuntimeError("Cumplimiento DB/auth block does not match reviewed source")
    start = text.index(INFRA_START)
    end = text.index(INFRA_END, start)
    text = text[:start] + NEW_INFRA + text[end:]

    text = _replace_once(text, OLD_DOC_UPLOAD, NEW_DOC_UPLOAD, "document upload")
    text = _replace_once(text, OLD_SIGN, NEW_SIGN, "signed document URL")
    text = _replace_once(text, OLD_SIGN_RETURN, NEW_SIGN_RETURN, "signed URL return")
    text = _replace_once(text, OLD_XML_UPLOAD, NEW_XML_UPLOAD, "XML upload")
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    compile(updated, "routers/cumplimiento.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
