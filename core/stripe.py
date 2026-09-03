"""Shared Stripe subscription configuration and infrastructure helpers."""
from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import HTTPException

from core.config import settings
from core.database import get_rows, patch_rows, patch_rows_ignoring_http_status
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


async def get_or_create_stripe_customer(user_id: str, email: str, nombre: str) -> str:
    """Preserve the legacy Stripe customer lookup/create/write-through contract."""
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "stripe_customer_id,nombre"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        rows = []
    row = rows[0] if rows else {}

    if row.get("stripe_customer_id"):
        return row["stripe_customer_id"]

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.stripe.com/v1/customers",
            headers=stripe_headers(),
            data={"name": nombre or email, "email": email, "metadata[user_id]": user_id},
        )
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Stripe crear customer: {response.text}")
    customer_id = response.json().get("id")

    try:
        await patch_rows(
            "usuarios",
            {"id": f"eq.{user_id}"},
            {"stripe_customer_id": customer_id},
            prefer="return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: Supabase HTTP rejection did not abort customer creation.
        pass

    return customer_id


async def activate_enterprise_subscription(
    org_id: str,
    user_id: str,
    asientos: int,
    nombre_empresa: str = "",
) -> None:
    """Preserve the legacy post-payment organization activation sequence."""
    payload = {
        "tipo": "empresa",
        "plan": "Broquer para Empresas",
        "asientos_max": int(asientos),
        "activo": True,
        "vence_el": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if nombre_empresa:
        payload["nombre"] = nombre_empresa[:120]
    await patch_rows_ignoring_http_status(
        "organizaciones", {"id": f"eq.{org_id}"}, payload
    )
    await patch_rows_ignoring_http_status(
        "organizacion_miembros",
        {"user_id": f"eq.{user_id}", "org_id": f"eq.{org_id}"},
        {"rol_org": "owner"},
    )
