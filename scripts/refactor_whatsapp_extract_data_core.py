#!/usr/bin/env python3
"""Extract WhatsApp 2 database compatibility adapters from whatsapp.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
IMPORT = "from routers.whatsapp_data import sb_delete, sb_get, sb_patch, sb_post\n"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
BLOCK_START = "# =============================================================================\n# Helpers de Supabase — compatibilidad sobre Core\n# =============================================================================\n"
BLOCK_END = "async def _require_user(request: Request) -> str:\n"


def transform_source(source: str) -> str:
    transformed = source

    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if BLOCK_START in transformed:
        start = transformed.index(BLOCK_START)
        end = transformed.find(BLOCK_END, start)
        if end == -1:
            raise RuntimeError("WhatsApp helper block end not found")
        transformed = transformed[:start] + transformed[end:]
    elif "async def sb_get(" in transformed or "async def sb_post(" in transformed or "async def sb_patch(" in transformed or "async def sb_delete(" in transformed:
        raise RuntimeError("Partial WhatsApp database helper extraction detected")

    for name in ("sb_get", "sb_post", "sb_patch", "sb_delete"):
        if f"async def {name}(" in transformed:
            raise RuntimeError(f"{name} implementation still present in whatsapp.py")

    if IMPORT not in transformed:
        raise RuntimeError("WhatsApp data adapter import missing")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    SOURCE.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
