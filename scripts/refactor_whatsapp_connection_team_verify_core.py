#!/usr/bin/env python3
"""Allow owners/admins to verify WhatsApp numbers they are already allowed to manage."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "whatsapp_connection.py"

OLD = '''async def wa2_numero_verificar(numero_id: str, request: Request):
    user_id = await _require_user(request)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": f"eq.{user_id}",
                                        "select": "waba_id,access_token", "limit": "1"})
'''
NEW = '''async def wa2_numero_verificar(numero_id: str, request: Request):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                        "select": "waba_id,access_token", "limit": "1"})
'''


def transform_source(source: str) -> str:
    if OLD in source:
        transformed = source.replace(OLD, NEW, 1)
    elif NEW in source:
        transformed = source
    else:
        raise RuntimeError("number verification authorization anchor not found")

    if '"user_id": f"eq.{user_id}"' in transformed[
        transformed.index("async def wa2_numero_verificar"):
        transformed.index('@router.get("/numeros")')
    ]:
        raise RuntimeError("exact-user verification filter remains")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
