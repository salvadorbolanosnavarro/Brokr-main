#!/usr/bin/env python3
"""Extract individual Stripe checkout from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

MOUNT = '''# Checkout web de suscripción individual.\nfrom routers.subscription_checkout import router as subscription_checkout_router\napp.include_router(subscription_checkout_router)\n\n'''
START = 'class CheckoutRequest(BaseModel):'
END = '# ════════════════════════════════════════════════════════════════\n# BROQUER PARA EMPRESAS — contratación y lugares'


def transform_source(source: str) -> str:
    if START not in source:
        if MOUNT in source and '@app.post("/subscription/checkout")' not in source and 'async def _get_or_create_stripe_customer' not in source:
            compile(source, str(MAIN), "exec")
            return source
        raise RuntimeError("subscription checkout start marker not found")
    if source.count(START) != 1 or source.count('@app.post("/subscription/checkout")') != 1:
        raise RuntimeError("unexpected subscription checkout marker count")
    start = source.index(START)
    end = source.index(END, start)
    transformed = source[:start] + source[end:]

    anchor = '# Cancelación de suscripción web.\n'
    idx = transformed.index(anchor)
    if MOUNT not in transformed:
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if '@app.post("/subscription/checkout")' in transformed:
        raise RuntimeError("subscription checkout route still present in main")
    if 'async def _get_or_create_stripe_customer' in transformed:
        raise RuntimeError("Stripe customer helper still present in main")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
