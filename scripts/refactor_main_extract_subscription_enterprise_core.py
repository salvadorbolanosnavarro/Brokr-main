#!/usr/bin/env python3
"""Extract Broquer para Empresas subscription domain from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'async def _exigir_admin_de_org(request: Request) -> dict:'
END = '@app.post("/subscription/webhook")'
MOUNT = '''# Suscripción de Broquer para Empresas.\nfrom routers.subscription_enterprise import router as subscription_enterprise_router\napp.include_router(subscription_enterprise_router)\n\n'''
STRIPE_IMPORT_OLD = '''    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,\n    get_or_create_stripe_customer as _get_or_create_stripe_customer,\n    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,\n)'''
STRIPE_IMPORT_NEW = '''    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TRIAL_MAX_DIAS,\n    activate_enterprise_subscription as _activar_empresa,\n    get_or_create_stripe_customer as _get_or_create_stripe_customer,\n    precio_empresa as _precio_empresa, stripe_headers as _stripe_headers,\n)'''


def transform_source(source: str) -> str:
    enterprise_routes = (
        '@app.get("/subscription/empresa/plan")',
        '@app.post("/subscription/empresa/checkout")',
        '@app.post("/subscription/empresa/asientos")',
    )

    if START not in source:
        if MOUNT in source and all(route not in source for route in enterprise_routes):
            if STRIPE_IMPORT_NEW not in source:
                raise RuntimeError("enterprise activation Core alias missing")
            if 'async def _activar_empresa(' in source:
                raise RuntimeError("local enterprise activation helper still present")
            compile(source, str(MAIN), "exec")
            return source
        raise RuntimeError("enterprise subscription start marker not found")

    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("unexpected enterprise subscription boundary count")
    if any(source.count(route) != 1 for route in enterprise_routes):
        raise RuntimeError("unexpected enterprise route count")

    start = source.index(START)
    end = source.index(END, start)
    transformed = source[:start] + source[end:]

    if STRIPE_IMPORT_NEW not in transformed:
        if transformed.count(STRIPE_IMPORT_OLD) != 1:
            raise RuntimeError("Stripe Core import anchor not found")
        transformed = transformed.replace(STRIPE_IMPORT_OLD, STRIPE_IMPORT_NEW, 1)

    anchor = '# Checkout web de suscripción individual.\n'
    idx = transformed.index(anchor)
    if MOUNT not in transformed:
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for route in enterprise_routes:
        if route in transformed:
            raise RuntimeError(f"enterprise route still present in main: {route}")
    for helper in (
        'async def _exigir_admin_de_org(',
        'def _valida_asientos(',
        'async def _ocupacion_org(',
        'async def _activar_empresa(',
    ):
        if helper in transformed:
            raise RuntimeError(f"enterprise helper still present in main: {helper}")
    if 'await _activar_empresa(_org_id, user_id, _asientos,' not in transformed:
        raise RuntimeError("Stripe webhook lost enterprise activation consumer")

    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
