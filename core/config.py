"""Canonical Broquer runtime configuration.

This module is the single source of truth for environment variable names and
security-sensitive fallback policy. Domain modules should import settings from
here rather than reading environment variables directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "si", "sí", "on"}


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _env_nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_nonnegative_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    app_url: str
    api_base_url: str
    anthropic_api_key: str
    anthropic_base: str
    groq_api_key: str
    groq_base: str
    gemini_api_key: str
    gemini_image_model: str
    easybroker_api_key: str
    apify_api_key: str
    google_places_key: str
    banxico_token: str
    banxico_series_udis: str
    banxico_series_inpc: str
    legacy_main_frontend_url: str
    legacy_main_fb_app_id: str
    legacy_main_fb_app_secret: str
    resend_api_key: str
    resend_from: str
    resend_reply_to: str
    correo_relay_from: str
    correo_secret: str
    correo_webhook_token: str
    stripe_secret_key: str
    monthly_price_mxn: float
    wa_plantilla_otp: str
    meta_app_id: str
    meta_app_secret: str
    meta_login_config_id: str
    meta_graph_version: str
    wa_register_pin: str
    frontend_url: str
    ai_require_session: bool
    hourly_anonymous_limit: int
    hourly_user_limit: int
    apns_key_p8: str
    apns_key_id: str
    apns_team_id: str
    apns_bundle_id: str
    apns_env: str
    wa2_model: str
    wa2_meta_app_id: str
    wa2_meta_app_secret: str
    wa2_verify_token: str
    wa2_app_secret: str
    wa2_register_pin: str
    wa2_webhook_url: str
    wa2_broquer_api_base: str
    wa2_zone_default: str
    wa2_debounce_seconds: int
    wa2_campaign_limit: int
    wa2_media_bucket: str
    wa2_ai_limit: int

    @classmethod
    def from_env(cls) -> "Settings":
        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        # Supabase's current public client key is the publishable key. Keep the
        # legacy anon names as temporary fallbacks so production can migrate
        # without downtime; once Railway is on SUPABASE_PUBLISHABLE_KEY the
        # legacy keys can be disabled in Supabase.
        supabase_anon_key = (
            os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
            or os.getenv("SUPABASE_ANON_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
        )
        # Security policy: privileged credentials never silently fall back to
        # the public/anonymous key. SUPABASE_SERVICE_KEY may contain either a
        # current sb_secret_ key or a legacy service_role key during migration.
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")

        wa2_meta_app_secret = os.getenv("META_APP_SECRET", "")

        return cls(
            supabase_url=supabase_url,
            supabase_anon_key=supabase_anon_key,
            supabase_service_key=supabase_service_key,
            app_url=os.getenv("APP_URL", "https://broquer.app").rstrip("/"),
            api_base_url=os.getenv("API_BASE_URL", "https://api.broquer.app").rstrip("/"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_base=os.getenv("ANTHROPIC_BASE", "https://api.anthropic.com/v1").rstrip("/"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_base=os.getenv("GROQ_BASE", "https://api.groq.com/openai/v1").rstrip("/"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_image_model=os.getenv(
                "GEMINI_IMAGE_MODEL",
                "gemini-3.1-flash-image-preview",
            ),
            easybroker_api_key=os.getenv("EB_API_KEY", ""),
            apify_api_key=os.getenv("APIFY_API_KEY", ""),
            google_places_key=os.getenv("GOOGLE_PLACES_KEY", ""),
            banxico_token=(
                os.getenv("BANXICO_TOKEN", "").strip().strip('"').strip("'")
            ),
            banxico_series_udis=os.getenv("BANXICO_SERIE_UDIS", "SP68257"),
            banxico_series_inpc=os.getenv("BANXICO_SERIE_INPC", "SP74625"),
            # Temporary compatibility values for main.py while its legacy
            # configuration block is migrated. Do not reuse these in new modules.
            legacy_main_frontend_url=os.getenv(
                "FRONTEND_URL",
                "https://app.navarroai.com.mx",
            ),
            legacy_main_fb_app_id=os.getenv("FB_APP_ID", ""),
            legacy_main_fb_app_secret=os.getenv("FB_APP_SECRET", ""),
            resend_api_key=os.getenv("RESEND_API_KEY", ""),
            resend_from=os.getenv("RESEND_FROM", "Broquer <hola@broquer.app>"),
            resend_reply_to=os.getenv("RESEND_REPLY_TO", "").strip(),
            correo_relay_from=os.getenv(
                "CORREO_RELAY_FROM",
                "correo@broquer.app",
            ),
            correo_secret=os.getenv("CORREO_SECRET", ""),
            correo_webhook_token=os.getenv("CORREO_WEBHOOK_TOKEN", "").strip(),
            stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", "").strip(),
            monthly_price_mxn=_env_nonnegative_float("PRECIO_MENSUAL_MXN", 499.0),
            wa_plantilla_otp=os.getenv("WA_PLANTILLA_OTP", ""),
            meta_app_id=os.getenv("META_APP_ID", "") or os.getenv("FB_APP_ID", ""),
            meta_app_secret=(
                os.getenv("META_APP_SECRET", "")
                or os.getenv("WA_APP_SECRET", "")
                or os.getenv("FB_APP_SECRET", "")
            ),
            meta_login_config_id=(
                os.getenv("META_LOGIN_CONFIG_ID", "")
                or os.getenv("WA_EMBEDDED_SIGNUP_CONFIG_ID", "")
            ),
            meta_graph_version=os.getenv("META_GRAPH_VERSION", "v23.0"),
            wa_register_pin=os.getenv("WA_REGISTER_PIN", "123456"),
            frontend_url=os.getenv("FRONTEND_URL", "https://broquer.app").rstrip("/"),
            ai_require_session=_env_bool("EXIGIR_SESION_IA", default=False),
            hourly_anonymous_limit=_env_positive_int("TOPE_HORA_ANONIMO", 40),
            hourly_user_limit=_env_positive_int("TOPE_HORA_USUARIO", 400),
            apns_key_p8=os.getenv("APNS_KEY_P8", "").replace("\\n", "\n").strip(),
            apns_key_id=os.getenv("APNS_KEY_ID", "").strip(),
            apns_team_id=os.getenv("APNS_TEAM_ID", "").strip(),
            apns_bundle_id=os.getenv("APNS_BUNDLE_ID", "com.broquer.app").strip(),
            apns_env=os.getenv("APNS_ENV", "prod").strip().lower(),
            wa2_model=os.getenv("WA2_MODEL", "claude-sonnet-4-6"),
            wa2_meta_app_id=os.getenv("META_APP_ID", "1709238933850389"),
            wa2_meta_app_secret=wa2_meta_app_secret,
            wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "broquer2_verify"),
            wa2_app_secret=os.getenv("WA_APP_SECRET", "") or wa2_meta_app_secret,
            wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857"),
            wa2_webhook_url=os.getenv(
                "WA2_WEBHOOK_URL",
                "https://api.broquer.app/whatsapp2/webhook",
            ),
            wa2_broquer_api_base=os.getenv(
                "BROQUER_API_BASE",
                "https://api.broquer.app",
            ).rstrip("/"),
            wa2_zone_default=os.getenv("WA2_ZONA_DEFAULT", "America/Mexico_City"),
            wa2_debounce_seconds=_env_nonnegative_int("WA2_DEBOUNCE_SEG", 8),
            wa2_campaign_limit=_env_positive_int("WA2_CAMPANA_TOPE", 250),
            wa2_media_bucket=os.getenv("WA_MEDIA_BUCKET", "wa-media"),
            wa2_ai_limit=_env_positive_int("WA2_TOPE_IA", 25),
        )

    def require_supabase_public(self) -> None:
        if not self.supabase_url or not self.supabase_anon_key:
            raise RuntimeError("Supabase public configuration is incomplete")

    def require_supabase_service(self) -> None:
        self.require_supabase_public()
        if not self.supabase_service_key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is required for privileged operations")

    def require_correo_secret(self) -> str:
        """Return the key material used to encrypt stored email credentials.

        The explicit ``CORREO_SECRET`` is preferred. For backwards
        compatibility, the service-role key remains a valid fallback; unlike
        the old router, the anonymous Supabase key is never accepted here.
        """
        secret = self.correo_secret or self.supabase_service_key
        if not secret:
            raise RuntimeError(
                "CORREO_SECRET or SUPABASE_SERVICE_KEY is required for email credential encryption"
            )
        return secret


settings = Settings.from_env()
