"""Shared Stripe subscription configuration and pure pricing helpers."""
from __future__ import annotations

from core.config import settings
from core.legacy_main_config import legacy_main_settings

STRIPE_SECRET_KEY = settings.stripe_secret_key
STRIPE_WEBHOOK_SECRET = legacy_main_settings.stripe_webhook_secret

STRIPE_PRICE_PRO = legacy_main_settings.stripe_price_pro
STRIPE_PRICE_AMPI = legacy_main_settings.stripe_price_ampi
STRIPE_PRICE_EMPRESA_MENSUAL = legacy_main_settings.stripe_price_empresa_mensual
STRIPE_PRICE_EMPRESA_ANUAL = legacy_main_settings.stripe_price_empresa_anual
STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL = legacy_main_settings.stripe_price_empresa_extra_mensual
STRIPE_PRICE_EMPRESA_EXTRA_ANUAL = legacy_main_settings.stripe_price_empresa_extra_anual

EMPRESA_ASIENTOS_BASE = 5
EMPRESA_ASIENTOS_MAX = 500
EMPRESA_TARIFAS = {
    "mensual": {"base": 3499, "extra": 599, "etiqueta": "al mes"},
    "anual": {"base": 38489, "extra": 6589, "etiqueta": "al año"},
}

TRIAL_MAX_DIAS = 7
PROMO_CODE_AMPI = "ampi2026"


def stripe_headers() -> dict:
    return {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def precio_empresa(periodo: str, extra: bool = False) -> str:
    """Return the configured Stripe price id for an enterprise period."""
    if periodo == "anual":
        return STRIPE_PRICE_EMPRESA_EXTRA_ANUAL if extra else STRIPE_PRICE_EMPRESA_ANUAL
    return STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL if extra else STRIPE_PRICE_EMPRESA_MENSUAL
