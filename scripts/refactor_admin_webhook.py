#!/usr/bin/env python3
"""Apply the one-time fail-closed webhook refactor to admin_consola.py.

The transform is intentionally exact and idempotence-resistant: it aborts if
Broquer's current source no longer matches the reviewed legacy block. This is
safer than reconstructing a large source file through an external editor.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "admin_consola.py"

IMPORT_ANCHOR = "from pydantic import BaseModel\n"
IMPORT_REPLACEMENT = (
    "from pydantic import BaseModel\n\n"
    "from core.webhooks import require_shared_secret\n"
)

LEGACY_BLOCK = '''    if CORREO_WEBHOOK_TOKEN:\n        recibido = request.headers.get("x-broquer-token", "") or request.query_params.get("token", "")\n        if recibido != CORREO_WEBHOOK_TOKEN:\n            raise HTTPException(status_code=401, detail="Token inválido.")\n'''

SAFE_BLOCK = '''    require_shared_secret(\n        request,\n        CORREO_WEBHOOK_TOKEN,\n        header_name="x-broquer-token",\n        query_name="token",\n    )\n'''


def transform(text: str) -> str:
    if "from core.webhooks import require_shared_secret" in text:
        raise RuntimeError("admin webhook refactor already appears to be applied")
    if text.count(IMPORT_ANCHOR) != 1:
        raise RuntimeError("expected one pydantic import anchor")
    if text.count(LEGACY_BLOCK) != 1:
        raise RuntimeError("legacy webhook block does not match reviewed source")

    text = text.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT, 1)
    text = text.replace(LEGACY_BLOCK, SAFE_BLOCK, 1)
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(ROOT)} to fail-closed webhook auth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
