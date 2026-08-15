#!/usr/bin/env python3
"""Migrate WhatsApp 2 runtime config and authentication to Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"WhatsApp {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.auth import require_user_id" in text:
        raise RuntimeError("WhatsApp config/auth refactor already appears applied")

    text = _replace_once(text, "import os\n", "", "os import")
    text = _replace_once(
        text,
        "from pydantic import BaseModel\n",
        '''from pydantic import BaseModel\n\nfrom core.auth import require_user_id\nfrom core.config import settings\n''',
        "Core imports",
    )

    replacements = {
        'SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").rstrip("/")':
            'SUPABASE_URL         = settings.supabase_url',
        'SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")':
            'SUPABASE_ANON_KEY    = settings.supabase_anon_key',
        'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY':
            'SUPABASE_SERVICE_KEY = settings.supabase_service_key',
        'ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")':
            'ANTHROPIC_API_KEY = settings.anthropic_api_key',
        'ANTHROPIC_BASE    = os.environ.get("ANTHROPIC_BASE", "https://api.anthropic.com/v1")':
            'ANTHROPIC_BASE    = settings.anthropic_base',
        'WA2_MODEL         = os.environ.get("WA2_MODEL", "claude-sonnet-4-6")':
            'WA2_MODEL         = settings.wa2_model',
        'META_APP_ID     = os.environ.get("META_APP_ID", "1709238933850389")':
            'META_APP_ID     = settings.wa2_meta_app_id',
        'META_APP_SECRET = os.environ.get("META_APP_SECRET", "")':
            'META_APP_SECRET = settings.wa2_meta_app_secret',
        'WA2_VERIFY_TOKEN = os.environ.get("WA2_VERIFY_TOKEN", "broquer2_verify")':
            'WA2_VERIFY_TOKEN = settings.wa2_verify_token',
        'WA2_APP_SECRET   = os.environ.get("WA_APP_SECRET", "") or META_APP_SECRET':
            'WA2_APP_SECRET   = settings.wa2_app_secret',
        'WA2_REGISTER_PIN = os.environ.get("WA_REGISTER_PIN", "142857")':
            'WA2_REGISTER_PIN = settings.wa2_register_pin',
        'WA2_WEBHOOK_URL  = os.environ.get("WA2_WEBHOOK_URL", "https://api.broquer.app/whatsapp2/webhook")':
            'WA2_WEBHOOK_URL  = settings.wa2_webhook_url',
        'BROQUER_API_BASE = os.environ.get("BROQUER_API_BASE", "https://api.broquer.app")':
            'BROQUER_API_BASE = settings.wa2_broquer_api_base',
        '_ZONA_DEFAULT = os.environ.get("WA2_ZONA_DEFAULT", "America/Mexico_City")':
            '_ZONA_DEFAULT = settings.wa2_zone_default',
        'WA_MEDIA_BUCKET = os.environ.get("WA_MEDIA_BUCKET", "wa-media")':
            'WA_MEDIA_BUCKET = settings.wa2_media_bucket',
        'GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")':
            'GROQ_API_KEY = settings.groq_api_key',
        'GROQ_BASE    = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")':
            'GROQ_BASE    = settings.groq_base',
    }
    for old, new in replacements.items():
        text = _replace_once(text, old, new, old)

    text = _replace_once(
        text,
        '''try:\n    WA2_DEBOUNCE = max(0, int(os.environ.get("WA2_DEBOUNCE_SEG", "8")))\nexcept Exception:\n    WA2_DEBOUNCE = 8\n''',
        'WA2_DEBOUNCE = settings.wa2_debounce_seconds\n',
        "debounce config",
    )
    text = _replace_once(
        text,
        '''try:\n    WA2_CAMPANA_TOPE = max(1, int(os.environ.get("WA2_CAMPANA_TOPE", "250")))\nexcept Exception:\n    WA2_CAMPANA_TOPE = 250\n''',
        'WA2_CAMPANA_TOPE = settings.wa2_campaign_limit\n',
        "campaign limit config",
    )
    text = _replace_once(
        text,
        '''try:\n    WA2_TOPE_IA = max(1, int(os.environ.get("WA2_TOPE_IA", "25")))\nexcept Exception:\n    WA2_TOPE_IA = 25\n''',
        'WA2_TOPE_IA = settings.wa2_ai_limit\n',
        "AI limit config",
    )

    auth_start = "async def get_user_id_from_token(request: Request) -> str | None:\n"
    auth_end = "\n\nasync def _ids_visibles(user_id: str) -> list[str]:\n"
    if text.count(auth_start) != 1 or text.count(auth_end) != 1:
        raise RuntimeError("WhatsApp auth block does not match reviewed source")
    start = text.index(auth_start)
    end = text.index(auth_end, start)
    new_auth = '''async def _require_user(request: Request) -> str:\n    return await require_user_id(request, detail="No autorizado")\n'''
    text = text[:start] + new_auth + text[end:]
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "whatsapp.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
