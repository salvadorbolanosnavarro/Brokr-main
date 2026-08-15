#!/usr/bin/env python3
"""Complete the Organizaciones Core migration with safe compatibility aliases."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "organizaciones.py"

OLD = '''APP_URL = settings.app_url
PERMISOS_VALIDOS = set(VALID_PERMISSIONS)
'''
NEW = '''# Compatibility aliases used by the existing organization-context guard.
# Values come from Core; no environment name or fallback policy lives here.
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key
APP_URL = settings.app_url
PERMISOS_VALIDOS = set(VALID_PERMISSIONS)
'''


def transform(text: str) -> str:
    if text.count(OLD) != 1:
        raise RuntimeError("Organizaciones Core alias insertion point does not match reviewed source")
    updated = text.replace(OLD, NEW, 1)
    compile(updated, "routers/organizaciones.py", "exec")
    return updated


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    TARGET.write_text(transform(original), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
