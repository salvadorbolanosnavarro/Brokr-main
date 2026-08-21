#!/usr/bin/env python3
"""Replace inline Meta delivery failure handling with a shared service."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_delivery_status import procesar_statuses as _procesar_statuses\n"
START = "            # ── Acuses de Meta (enviado / entregado / leído / FALLIDO) ──────\n"
END = "    return True, trabajo\n"
REPLACEMENT = "            await _procesar_statuses(val, numero)\n"


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "await _procesar_statuses(val, numero)" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("delivery-status block start not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("persist-incoming return anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    if 'for st in val.get("statuses", []):' in transformed:
        raise RuntimeError("inline delivery-status loop remains")
    if "await _procesar_statuses(val, numero)" not in transformed:
        raise RuntimeError("delivery-status delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
