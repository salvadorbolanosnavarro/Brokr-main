#!/usr/bin/env python3
"""Extract the Stripe subscription webhook from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = '@app.post("/subscription/webhook")'
END = '# ════════════════════════════════════════════════════════════════\n# Contactos / Importar desde EasyBroker'
MOUNT = '''# Webhook de suscripciones web vía Stripe.\nfrom routers.stripe_webhook import router as stripe_webhook_router\napp.include_router(stripe_webhook_router)\n\n'''
DEAD_ALIAS = '    activate_enterprise_subscription as _activar_empresa,\n'


def transform_source(source: str) -> str:
    if START not in source:
        transformed = source.replace(DEAD_ALIAS, "", 1)
        if MOUNT in transformed and 'async def stripe_webhook(' not in transformed:
            compile(transformed, str(MAIN), "exec")
            return transformed
        raise RuntimeError("Stripe webhook start marker not found")
    if source.count(START) != 1:
        raise RuntimeError(f"Expected one Stripe webhook route, found {source.count(START)}")

    start = source.index(START)
    end = source.index(END, start)
    transformed = source[:start] + source[end:]
    transformed = transformed.replace(DEAD_ALIAS, "", 1)

    anchor = '# Webhook de suscripciones iOS vía RevenueCat.\n'
    idx = transformed.index(anchor)
    if MOUNT not in transformed:
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if START in transformed or 'async def stripe_webhook(' in transformed:
        raise RuntimeError("Stripe webhook implementation still present in main")
    if 'activate_enterprise_subscription as _activar_empresa' in transformed:
        raise RuntimeError("dead Stripe webhook enterprise activation alias still present in main")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
