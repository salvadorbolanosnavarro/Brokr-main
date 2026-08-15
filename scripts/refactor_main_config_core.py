#!/usr/bin/env python3
"""One-shot exact transform that moves main.py env reads behind core.config."""
from __future__ import annotations

from pathlib import Path


OLD = '''EB_API_KEY       = os.environ.get("EB_API_KEY", "") or _config.get("eb_api_key", "")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
EB_BASE          = "https://api.easybroker.com/v1"
GROQ_BASE        = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE   = "https://api.anthropic.com/v1"
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta"
APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "")
GOOGLE_PLACES_KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY      = os.environ.get("SUPABASE_ANON_KEY", "")
FB_APP_ID     = os.environ.get("FB_APP_ID", "")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET", "")
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "https://app.navarroai.com.mx")
# Banxico SIE — INPC + UDIS para calculadora ISR
BANXICO_TOKEN     = os.environ.get("BANXICO_TOKEN", "").strip().strip('"').strip("'")
BANXICO_BASE      = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = os.environ.get("BANXICO_SERIE_UDIS", "SP68257")  # Valor de UDIS (diaria)
BANXICO_SERIE_INPC = os.environ.get("BANXICO_SERIE_INPC", "SP74625")  # INPC mensual base 2Q-jul-2018=100
'''

NEW = '''# Compatibility aliases while main.py is progressively decomposed. All runtime
# environment names and public/privileged Supabase key policy live in core.config.
EB_API_KEY       = settings.easybroker_api_key or _config.get("eb_api_key", "")
GROQ_API_KEY     = settings.groq_api_key
ANTHROPIC_API_KEY = settings.anthropic_api_key
GEMINI_API_KEY    = settings.gemini_api_key
EB_BASE          = "https://api.easybroker.com/v1"
GROQ_BASE        = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE   = "https://api.anthropic.com/v1"
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta"
APIFY_API_KEY = settings.apify_api_key
GOOGLE_PLACES_KEY = settings.google_places_key
SUPABASE_URL      = settings.supabase_url
SUPABASE_KEY      = settings.supabase_anon_key
FB_APP_ID     = settings.legacy_main_fb_app_id
FB_APP_SECRET = settings.legacy_main_fb_app_secret
FRONTEND_URL  = settings.legacy_main_frontend_url
# Banxico SIE — INPC + UDIS para calculadora ISR
BANXICO_TOKEN     = settings.banxico_token
BANXICO_BASE      = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = settings.banxico_series_udis  # Valor de UDIS (diaria)
BANXICO_SERIE_INPC = settings.banxico_series_inpc  # INPC mensual base 2Q-jul-2018=100
'''


def transform(source: str) -> str:
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f"Expected exactly one main config block, found {count}")
    updated = source.replace(OLD, NEW, 1)
    if "os.environ.get(" in updated or "os.getenv(" in updated:
        raise RuntimeError("Direct environment reads remain in main.py after transform")
    compile(updated, "main.py", "exec")
    return updated


def main() -> None:
    path = Path("main.py")
    source = path.read_text(encoding="utf-8")
    updated = transform(source)
    if updated == source:
        raise RuntimeError("Transform made no change")
    path.write_text(updated, encoding="utf-8")
    print("main.py configuration now delegates to core.config")


if __name__ == "__main__":
    main()
