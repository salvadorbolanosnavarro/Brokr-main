#!/usr/bin/env python3
"""Extract individual Stripe checkout from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

MOUNT = '''# Checkout web de suscripción individual.\nfrom routers.subscription_checkout import router as subscription_checkout_router\napp.include_router(subscription_checkout_router)\n\n'''
START = 'class CheckoutRequest(BaseModel):'
END = '# ════════════════════════════════════════════════════════════════\n# BROQUER PARA EMPRESAS — contratación y lugares'
STRIPE_IMPORT_OLD = '''    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,\n    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,\n)'''
STRIPE_IMPORT_NEW = '''    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,\n    get_or_create_stripe_customer as _get_or_create_stripe_customer,\n    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,\n)'''


def transform_source(source: str) -> str:
    if START not in source:
        if MOUNT in source and '@app.post("/subscription/checkout")' not in source and 'async def _get_or_create_stripe_customer' not in source:
            if STRIPE_IMPORT_NEW not in source:
                raise RuntimeError("shared Stripe customer helper alias missing")
            compile(source, str(MAIN), "exec")
            return source
        raise RuntimeError("subscription checkout start marker not found")
    if source.count(START) != 1 or source.count('@app.post("/subscription/checkout")') != 1:
        raise RuntimeError("unexpected subscription checkout marker count")
    start = source.index(START)
    end = source.index(END, start)
    transformed = source[:start] + source[end:]

    if STRIPE_IMPORT_NEW not in transformed:
        if transformed.count(STRIPE_IMPORT_OLD) != 1:
            raise RuntimeError("Stripe Core import anchor not found")
        transformed = transformed.replace(STRIPE_IMPORT_OLD, STRIPE_IMPORT_NEW, 1)

    anchor = '# Cancelación de suscripción web.\n'
    idx = transformed.index(anchor)
    if MOUNT not in transformed:
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if '@app.post("/subscription/checkout")' in transformed:
        raise RuntimeError("subscription checkout route still present in main")
    if 'async def _get_or_create_stripe_customer' in transformed:
        raise RuntimeError("Stripe customer helper still present in main")
    if '_get_or_create_stripe_customer(user_id, email, nombre)' not in transformed:
        raise RuntimeError("enterprise checkout lost shared Stripe customer helper consumer")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
