#!/usr/bin/env python3
"""One-shot exact transform that moves main.py env reads behind Core config."""
from __future__ import annotations

from pathlib import Path
import re


OLD_BLOCK = '''EB_API_KEY       = os.environ.get("EB_API_KEY", "") or _config.get("eb_api_key", "")
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

NEW_BLOCK = '''# Compatibility aliases while main.py is progressively decomposed. All runtime
# environment names and public/privileged Supabase key policy live in Core.
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


def _replace_exact(source: str, old: str, new: str, expected: int = 1) -> str:
    count = source.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} occurrence(s) of {old!r}, found {count}")
    return source.replace(old, new)


def transform(source: str) -> str:
    updated = _replace_exact(
        source,
        "from core.config import settings\n",
        "from core.config import settings\nfrom core.legacy_main_config import legacy_main_settings\n",
    )
    updated = _replace_exact(updated, OLD_BLOCK, NEW_BLOCK)

    replacements = [
        ('SEARCH_TIMEOUT = float(os.environ.get("AVM_SEARCH_TIMEOUT", "18"))', 'SEARCH_TIMEOUT = legacy_main_settings.avm_search_timeout'),
        ('FETCH_TIMEOUT = float(os.environ.get("AVM_FETCH_TIMEOUT", "10"))', 'FETCH_TIMEOUT = legacy_main_settings.avm_fetch_timeout'),
        ('MAX_SEARCH_RESULTS = int(os.environ.get("AVM_MAX_SEARCH_RESULTS", "16"))', 'MAX_SEARCH_RESULTS = legacy_main_settings.avm_max_search_results'),
        ('MAX_URLS_TO_FETCH = int(os.environ.get("AVM_MAX_URLS_TO_FETCH", "8"))', 'MAX_URLS_TO_FETCH = legacy_main_settings.avm_max_urls_to_fetch'),
        ('MAX_TEXT_CHARS_PER_URL = int(os.environ.get("AVM_MAX_TEXT_CHARS_PER_URL", "6500"))', 'MAX_TEXT_CHARS_PER_URL = legacy_main_settings.avm_max_text_chars_per_url'),
        ('FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")', 'FIRECRAWL_API_KEY = legacy_main_settings.firecrawl_api_key'),
        ('FIRECRAWL_CONCURRENCY = int(os.environ.get("FIRECRAWL_CONCURRENCY", "5"))', 'FIRECRAWL_CONCURRENCY = legacy_main_settings.firecrawl_concurrency'),
        ('FIRECRAWL_TIMEOUT = float(os.environ.get("FIRECRAWL_TIMEOUT", "45"))', 'FIRECRAWL_TIMEOUT = legacy_main_settings.firecrawl_timeout'),
        ('key = os.environ.get("GOOGLE_CSE_API_KEY", "") or os.environ.get("GOOGLE_SEARCH_API_KEY", "")', 'key = legacy_main_settings.google_cse_api_key'),
        ('cx = os.environ.get("GOOGLE_CSE_ID", "") or os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "")', 'cx = legacy_main_settings.google_cse_id'),
        ('key = os.environ.get("SERPAPI_API_KEY", "")', 'key = legacy_main_settings.serpapi_api_key'),
        ('key = os.environ.get("BRAVE_SEARCH_API_KEY", "")', 'key = legacy_main_settings.brave_search_api_key'),
        ('key = os.environ.get("TAVILY_API_KEY", "")', 'key = legacy_main_settings.tavily_api_key'),
        ('(os.environ.get("GOOGLE_CSE_API_KEY") or os.environ.get("GOOGLE_SEARCH_API_KEY"))', 'legacy_main_settings.google_cse_api_key'),
        ('(os.environ.get("GOOGLE_CSE_ID") or os.environ.get("GOOGLE_SEARCH_ENGINE_ID"))', 'legacy_main_settings.google_cse_id'),
        ('os.environ.get("SERPAPI_API_KEY")', 'legacy_main_settings.serpapi_api_key'),
        ('os.environ.get("BRAVE_SEARCH_API_KEY")', 'legacy_main_settings.brave_search_api_key'),
        ('os.environ.get("TAVILY_API_KEY")', 'legacy_main_settings.tavily_api_key'),
        ('os.environ.get("ANTHROPIC_AVM_MODEL", "claude-sonnet-4-6")', 'legacy_main_settings.anthropic_avm_model', 2),
        ('os.environ.get("GEMINI_IMAGE_MODEL", "")', 'settings.gemini_image_model'),
        ('os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")', 'settings.gemini_image_model'),
        ('_TOKEN_ENC_KEY = os.environ.get("TOKEN_ENC_KEY", "").strip()', '_TOKEN_ENC_KEY = legacy_main_settings.token_enc_key'),
        ('FB_API_VERSION = os.environ.get("FB_API_VERSION", "v21.0")', 'FB_API_VERSION = legacy_main_settings.fb_api_version'),
        ('_FB_USAR_PROOF = os.environ.get("FB_APPSECRET_PROOF", "1").strip().lower() not in ("0", "false", "no")', '_FB_USAR_PROOF = legacy_main_settings.fb_appsecret_proof'),
        ('FB_VERIFY_TOKEN = (os.environ.get("FB_VERIFY_TOKEN", "")\n                   or os.environ.get("META_VERIFY_TOKEN", ""))', 'FB_VERIFY_TOKEN = legacy_main_settings.fb_verify_token'),
        ('_FB_WEBHOOK_SECRET = os.environ.get("FB_WEBHOOK_SECRET", "") or FB_APP_SECRET', '_FB_WEBHOOK_SECRET = legacy_main_settings.fb_webhook_secret or FB_APP_SECRET'),
        ('FB_QA_ENABLED = os.environ.get("FB_QA_ENABLED", "").strip().lower() in ("1", "true", "yes")', 'FB_QA_ENABLED = legacy_main_settings.fb_qa_enabled'),
        ('FB_QA_AD_ACCOUNT_ID = os.environ.get("FB_QA_AD_ACCOUNT_ID", "").strip()', 'FB_QA_AD_ACCOUNT_ID = legacy_main_settings.fb_qa_ad_account_id'),
        ('FB_QA_PAGE_ID = os.environ.get("FB_QA_PAGE_ID", "").strip()', 'FB_QA_PAGE_ID = legacy_main_settings.fb_qa_page_id'),
        ('STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY", "")', 'STRIPE_SECRET_KEY      = settings.stripe_secret_key'),
        ('STRIPE_WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")', 'STRIPE_WEBHOOK_SECRET  = legacy_main_settings.stripe_webhook_secret'),
        ('STRIPE_PRICE_PRO       = os.environ.get("STRIPE_PRICE_PRO", "")', 'STRIPE_PRICE_PRO       = legacy_main_settings.stripe_price_pro'),
        ('STRIPE_PRICE_AMPI      = os.environ.get("STRIPE_PRICE_AMPI", "")', 'STRIPE_PRICE_AMPI      = legacy_main_settings.stripe_price_ampi'),
        ('STRIPE_PRICE_EMPRESA_MENSUAL       = os.environ.get("STRIPE_PRICE_EMPRESA_MENSUAL", "")', 'STRIPE_PRICE_EMPRESA_MENSUAL       = legacy_main_settings.stripe_price_empresa_mensual'),
        ('STRIPE_PRICE_EMPRESA_ANUAL         = os.environ.get("STRIPE_PRICE_EMPRESA_ANUAL", "")', 'STRIPE_PRICE_EMPRESA_ANUAL         = legacy_main_settings.stripe_price_empresa_anual'),
        ('STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL = os.environ.get("STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL", "")', 'STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL = legacy_main_settings.stripe_price_empresa_extra_mensual'),
        ('STRIPE_PRICE_EMPRESA_EXTRA_ANUAL   = os.environ.get("STRIPE_PRICE_EMPRESA_EXTRA_ANUAL", "")', 'STRIPE_PRICE_EMPRESA_EXTRA_ANUAL   = legacy_main_settings.stripe_price_empresa_extra_anual'),
        ('ACTIVATE_SECRET = os.environ.get("ACTIVATE_SECRET", "")', 'ACTIVATE_SECRET = legacy_main_settings.activate_secret'),
        ('DEMO_NOTIF_EMAIL = os.environ.get("DEMO_NOTIF_EMAIL", "hola@broquer.app")', 'DEMO_NOTIF_EMAIL = legacy_main_settings.demo_notif_email'),
        ('_RESEND_KEY_DEMO = os.environ.get("RESEND_API_KEY", "")', '_RESEND_KEY_DEMO = settings.resend_api_key'),
        ('_RESEND_FROM_DEMO = os.environ.get("RESEND_FROM", "Broquer <hola@broquer.app>")', '_RESEND_FROM_DEMO = settings.resend_from'),
        ("os.getenv('PORT', '8000')", 'legacy_main_settings.port'),
        ('tok = os.getenv("INSTAGRAM_TOKEN")', 'tok = legacy_main_settings.instagram_token'),
        ('ig_id = os.getenv("IG_USER_ID")', 'ig_id = legacy_main_settings.ig_user_id'),
    ]

    for item in replacements:
        if len(item) == 2:
            old, new = item
            expected = 1
        else:
            old, new, expected = item
        updated = _replace_exact(updated, old, new, expected)

    if re.search(r"\bos\.(?:getenv|environ)\b", updated):
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
    print("main.py configuration now delegates to Core configuration")


if __name__ == "__main__":
    main()
