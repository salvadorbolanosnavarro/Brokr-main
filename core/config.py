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
    groq_api_key: str
    gemini_api_key: str
    gemini_image_model: str
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

    @classmethod
    def from_env(cls) -> "Settings":
        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        supabase_anon_key = (
            os.getenv("SUPABASE_ANON_KEY", "")
            or os.getenv("SUPABASE_KEY", "")
        )
        # Security policy: privileged credentials never silently fall back to
        # the anonymous key. Callers requiring service-role access must fail
        # explicitly when this value is missing.
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")

        return cls(
            supabase_url=supabase_url,
            supabase_anon_key=supabase_anon_key,
            supabase_service_key=supabase_service_key,
            app_url=os.getenv("APP_URL", "https://broquer.app").rstrip("/"),
            api_base_url=os.getenv("API_BASE_URL", "https://api.broquer.app").rstrip("/"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_image_model=os.getenv(
                "GEMINI_IMAGE_MODEL",
                "gemini-3.1-flash-image-preview",
            ),
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
