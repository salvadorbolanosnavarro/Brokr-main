"""Canonical Broquer runtime configuration.

This module is the single source of truth for environment variable names and
security-sensitive fallback policy. Domain modules should import settings from
here rather than reading environment variables directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import os


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
        )

    def require_supabase_public(self) -> None:
        if not self.supabase_url or not self.supabase_anon_key:
            raise RuntimeError("Supabase public configuration is incomplete")

    def require_supabase_service(self) -> None:
        self.require_supabase_public()
        if not self.supabase_service_key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is required for privileged operations")


settings = Settings.from_env()
