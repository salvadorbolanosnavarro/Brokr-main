#!/usr/bin/env python3
"""Apply the one-time Admin Console config/auth migration to shared Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "admin_consola.py"

OLD_IMPORTS = '''import os
import html as _html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.webhooks import require_shared_secret
'''

NEW_IMPORTS = '''import html as _html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.admin import require_admin
from core.config import settings
from core.webhooks import require_shared_secret
'''

CONFIG_START = "# ── Config ────────────────────────────────────────────────────────────────\n"
CONFIG_END = "\n\ndef _sb_write_headers() -> Dict[str, str]:\n"
NEW_CONFIG = '''# ── Config ────────────────────────────────────────────────────────────────
# Compatibility aliases for the domain logic below. Environment-variable
# names and privileged credential policy live only in core.config.
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
SUPABASE_SERVICE_KEY = settings.supabase_service_key
STRIPE_SECRET_KEY = settings.stripe_secret_key
RESEND_API_KEY = settings.resend_api_key
RESEND_FROM = settings.resend_from
RESEND_REPLY_TO = settings.resend_reply_to
CORREO_WEBHOOK_TOKEN = settings.correo_webhook_token
PRECIO_MENSUAL_MXN = settings.monthly_price_mxn

SB_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
}
'''

AUTH_START = "# ── Autenticación ─────────────────────────────────────────────────────────\n"
AUTH_END = "# ── Lectura genérica de Supabase ──────────────────────────────────────────\n"


def transform(text: str) -> str:
    if "from core.admin import require_admin" in text:
        raise RuntimeError("Admin Core auth/config refactor already appears applied")
    if text.count(OLD_IMPORTS) != 1:
        raise RuntimeError("Admin import block does not match reviewed source")
    if text.count(CONFIG_START) != 1 or text.count(CONFIG_END) != 1:
        raise RuntimeError("Admin config block does not match reviewed source")
    if text.count(AUTH_START) != 1 or text.count(AUTH_END) != 1:
        raise RuntimeError("Admin auth block does not match reviewed source")

    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)

    config_start = text.index(CONFIG_START)
    config_end = text.index(CONFIG_END, config_start)
    text = text[:config_start] + NEW_CONFIG + text[config_end:]

    auth_start = text.index(AUTH_START)
    auth_end = text.index(AUTH_END, auth_start)
    text = text[:auth_start] + text[auth_end:]
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(ROOT)} to canonical Core auth/config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
