#!/usr/bin/env python3
"""Migrate Agente configuration and authentication to Core only."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "agente.py"

OLD_IMPORTS = '''import os
import json
import re
import time
import asyncio
import httpx
from typing import List, Optional
from limites import exigir_cupo, exigir_sesion
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
'''
NEW_IMPORTS = '''import json
import re
import time
import asyncio
import httpx
from typing import List, Optional
from limites import exigir_cupo, exigir_sesion
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
'''

OLD_CONFIG = '''# ── Config (mismas env vars que main.py) ──────────────────────────────────
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE       = "https://api.anthropic.com/v1"
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE            = "https://api.groq.com/openai/v1"
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY         = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY
'''
NEW_CONFIG = '''# ── Config ────────────────────────────────────────────────────────────────
# Environment names and privileged credential policy live only in Core.
ANTHROPIC_API_KEY    = settings.anthropic_api_key
ANTHROPIC_BASE       = "https://api.anthropic.com/v1"
GROQ_API_KEY         = settings.groq_api_key
GROQ_BASE            = "https://api.groq.com/openai/v1"
SUPABASE_URL         = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key
'''

AUTH_START = "# ── Auth: valida el JWT de Supabase y devuelve el user_id ─────────────────\n"
AUTH_END = "\ndef _sb_headers() -> dict:\n"


def transform(text: str) -> str:
    if "from core.auth import get_user_id_from_token" in text:
        raise RuntimeError("Agente config/auth refactor already appears applied")
    if text.count(OLD_IMPORTS) != 1:
        raise RuntimeError("Agente import block does not match reviewed source")
    if text.count(OLD_CONFIG) != 1:
        raise RuntimeError("Agente config block does not match reviewed source")
    if text.count(AUTH_START) != 1 or text.count(AUTH_END) != 1:
        raise RuntimeError("Agente auth block does not match reviewed source")

    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)
    text = text.replace(OLD_CONFIG, NEW_CONFIG, 1)
    start = text.index(AUTH_START)
    end = text.index(AUTH_END, start)
    text = text[:start] + text[end + 1:]
    text = text.replace("await _get_user_id(request)", "await get_user_id_from_token(request)")
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "routers/agente.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
