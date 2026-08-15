#!/usr/bin/env python3
"""Close two legacy security fallbacks in main.py without broad refactoring."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"

OLD_IMPORT_BLOCK = '''from fastapi.middleware.cors import CORSMiddleware
from limites import exigir_cupo, exigir_sesion
from pydantic import BaseModel
import httpx
'''
NEW_IMPORT_BLOCK = '''from fastapi.middleware.cors import CORSMiddleware
from limites import exigir_cupo, exigir_sesion
from pydantic import BaseModel
from core.config import settings
import httpx
'''

OLD_SERVICE_KEY = 'SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_KEY\n'
NEW_SERVICE_KEY = 'SUPABASE_SERVICE_KEY = settings.supabase_service_key\n'

OLD_ORG_BLOCK = '''try:
    from routers.organizaciones import (
        get_org_id_for_user, get_org_context, permiso_efectivo,
        exigir_gestion_integraciones,
    )
except Exception as _e:
    print(f"[org] No se pudo importar el contexto de organización: {_e}")
    async def get_org_id_for_user(user_id: str):
        return None
    async def get_org_context(user_id: str):
        return None
    def permiso_efectivo(ctx, clave):
        return False
    async def exigir_gestion_integraciones(request):
        return await get_user_id_from_token(request)
'''
NEW_ORG_BLOCK = '''from routers.organizaciones import (
    get_org_id_for_user, get_org_context, permiso_efectivo,
    exigir_gestion_integraciones,
)
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"main.py {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.config import settings" in text:
        raise RuntimeError("main security config cut already appears applied")
    text = _replace_once(text, OLD_IMPORT_BLOCK, NEW_IMPORT_BLOCK, "Core config import")
    text = _replace_once(text, OLD_SERVICE_KEY, NEW_SERVICE_KEY, "service-key fallback")
    text = _replace_once(text, OLD_ORG_BLOCK, NEW_ORG_BLOCK, "organization fail-open")
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "main.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
