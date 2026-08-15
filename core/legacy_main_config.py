"""Temporary canonical configuration for legacy main.py-only settings.

This module exists so the monolith no longer reads environment variables
throughout domain code. New modules must use dedicated Core/domain settings
instead. Delete fields here as each legacy main.py responsibility is extracted.
"""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LegacyMainSettings:
    avm_search_timeout: float
    avm_fetch_timeout: float
    avm_max_search_results: int
    avm_max_urls_to_fetch: int
    avm_max_text_chars_per_url: int
    firecrawl_api_key: str
    firecrawl_concurrency: int
    firecrawl_timeout: float
    google_cse_api_key: str
    google_cse_id: str
    serpapi_api_key: str
    brave_search_api_key: str
    tavily_api_key: str
    anthropic_avm_model: str
    token_enc_key: str
    fb_api_version: str
    fb_appsecret_proof: bool
    fb_verify_token: str
    fb_webhook_secret: str
    fb_qa_enabled: bool
    fb_qa_ad_account_id: str
    fb_qa_page_id: str
    stripe_webhook_secret: str
    stripe_price_pro: str
    stripe_price_ampi: str
    stripe_price_empresa_mensual: str
    stripe_price_empresa_anual: str
    stripe_price_empresa_extra_mensual: str
    stripe_price_empresa_extra_anual: str
    activate_secret: str
    revenuecat_webhook_auth: str
    demo_notif_email: str
    port: str
    instagram_token: str
    ig_user_id: str

    @classmethod
    def from_env(cls) -> "LegacyMainSettings":
        return cls(
            # Preserve main.py's historical parsing/defaults exactly. Invalid
            # numeric values therefore still fail fast at process startup.
            avm_search_timeout=float(os.getenv("AVM_SEARCH_TIMEOUT", "18")),
            avm_fetch_timeout=float(os.getenv("AVM_FETCH_TIMEOUT", "10")),
            avm_max_search_results=int(os.getenv("AVM_MAX_SEARCH_RESULTS", "16")),
            avm_max_urls_to_fetch=int(os.getenv("AVM_MAX_URLS_TO_FETCH", "8")),
            avm_max_text_chars_per_url=int(os.getenv("AVM_MAX_TEXT_CHARS_PER_URL", "6500")),
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", ""),
            firecrawl_concurrency=int(os.getenv("FIRECRAWL_CONCURRENCY", "5")),
            firecrawl_timeout=float(os.getenv("FIRECRAWL_TIMEOUT", "45")),
            google_cse_api_key=(
                os.getenv("GOOGLE_CSE_API_KEY", "")
                or os.getenv("GOOGLE_SEARCH_API_KEY", "")
            ),
            google_cse_id=(
                os.getenv("GOOGLE_CSE_ID", "")
                or os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
            ),
            serpapi_api_key=os.getenv("SERPAPI_API_KEY", ""),
            brave_search_api_key=os.getenv("BRAVE_SEARCH_API_KEY", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            anthropic_avm_model=os.getenv("ANTHROPIC_AVM_MODEL", "claude-sonnet-4-6"),
            token_enc_key=os.getenv("TOKEN_ENC_KEY", "").strip(),
            fb_api_version=os.getenv("FB_API_VERSION", "v21.0"),
            fb_appsecret_proof=(
                os.getenv("FB_APPSECRET_PROOF", "1").strip().lower()
                not in ("0", "false", "no")
            ),
            fb_verify_token=(
                os.getenv("FB_VERIFY_TOKEN", "")
                or os.getenv("META_VERIFY_TOKEN", "")
            ),
            fb_webhook_secret=os.getenv("FB_WEBHOOK_SECRET", ""),
            fb_qa_enabled=(
                os.getenv("FB_QA_ENABLED", "").strip().lower()
                in ("1", "true", "yes")
            ),
            fb_qa_ad_account_id=os.getenv("FB_QA_AD_ACCOUNT_ID", "").strip(),
            fb_qa_page_id=os.getenv("FB_QA_PAGE_ID", "").strip(),
            stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_pro=os.getenv("STRIPE_PRICE_PRO", ""),
            stripe_price_ampi=os.getenv("STRIPE_PRICE_AMPI", ""),
            stripe_price_empresa_mensual=os.getenv("STRIPE_PRICE_EMPRESA_MENSUAL", ""),
            stripe_price_empresa_anual=os.getenv("STRIPE_PRICE_EMPRESA_ANUAL", ""),
            stripe_price_empresa_extra_mensual=os.getenv("STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL", ""),
            stripe_price_empresa_extra_anual=os.getenv("STRIPE_PRICE_EMPRESA_EXTRA_ANUAL", ""),
            activate_secret=os.getenv("ACTIVATE_SECRET", ""),
            revenuecat_webhook_auth=os.getenv("REVENUECAT_WEBHOOK_AUTH", ""),
            demo_notif_email=os.getenv("DEMO_NOTIF_EMAIL", "hola@broquer.app"),
            port=os.getenv("PORT", "8000"),
            instagram_token=os.getenv("INSTAGRAM_TOKEN", ""),
            ig_user_id=os.getenv("IG_USER_ID", ""),
        )


legacy_main_settings = LegacyMainSettings.from_env()
