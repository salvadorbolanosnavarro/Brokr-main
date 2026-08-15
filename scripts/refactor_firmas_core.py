#!/usr/bin/env python3
"""Apply the one-time Firmas config/auth migration to shared Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "firmas.py"

OLD_IMPORTS = '''import os
import re
import io
import json
import html
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.subscriptions import require_paid_feature_access
'''

NEW_IMPORTS = '''import re
import io
import json
import html
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

import httpx
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.subscriptions import require_paid_feature_access
'''

CONFIG_START = "# ── Config (mismas env vars que main.py) ──────────────────────────────────\n"
CONFIG_END = "\nBUCKET = \"firmas\"\n"
NEW_CONFIG = '''# ── Config ────────────────────────────────────────────────────────────────
# Compatibility aliases for domain logic. Environment names and privileged
# credential policy live only in core.config.
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
APP_URL = settings.app_url
RESEND_API_KEY = settings.resend_api_key
RESEND_FROM = settings.resend_from
WA_PLANTILLA_OTP = settings.wa_plantilla_otp
'''

AUTH_START = "async def get_user_id_from_token(request: Request) -> Optional[str]:\n"
AUTH_END = "\n\nasync def _uid_max(request: Request) -> str:\n"
NEW_UID = '''async def _uid(request: Request) -> str:\n    return await require_user_id(\n        request,\n        detail="Inicia sesión para continuar.",\n    )\n'''


def transform(text: str) -> str:
    if "from core.auth import require_user_id" in text:
        raise RuntimeError("Firmas Core auth/config refactor already appears applied")
    if text.count(OLD_IMPORTS) != 1:
        raise RuntimeError("Firmas import block does not match reviewed source")
    if text.count(CONFIG_START) != 1 or text.count(CONFIG_END) != 1:
        raise RuntimeError("Firmas config block does not match reviewed source")
    if text.count(AUTH_START) != 1 or text.count(AUTH_END) != 1:
        raise RuntimeError("Firmas auth block does not match reviewed source")

    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)
    start = text.index(CONFIG_START)
    end = text.index(CONFIG_END, start)
    text = text[:start] + NEW_CONFIG + text[end:]

    start = text.index(AUTH_START)
    end = text.index(AUTH_END, start)
    text = text[:start] + NEW_UID + text[end:]
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(ROOT)} to canonical Core auth/config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
