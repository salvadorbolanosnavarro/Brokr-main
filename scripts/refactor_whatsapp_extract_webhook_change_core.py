#!/usr/bin/env python3
"""Reduce root webhook persistence to entry/change orchestration."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_webhook_change import procesar_change_value as _procesar_change_value\n"
)
START = "async def _persistir_entrantes(payload: dict):\n"
END = "async def _procesar_en_segundo_plano(item: dict):\n"
REPLACEMENT = '''async def _persistir_entrantes(payload: dict):\n    trabajo = []\n    for entry in payload.get("entry", []):\n        for change in entry.get("changes", []):\n            trabajo.extend(await _procesar_change_value(change.get("value", {})))\n    return True, trabajo\n\n\n'''


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "trabajo.extend(await _procesar_change_value(" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("persistir_entrantes start not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("background processor anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    body_start = transformed.find(START)
    body_end = transformed.find(END, body_start)
    body = transformed[body_start:body_end]
    for forbidden in (
        "phone_number_id =",
        "_procesar_coexistencia",
        "_persistir_mensaje_entrante",
        "_procesar_statuses",
    ):
        if forbidden in body:
            raise RuntimeError(f"root webhook persistence still owns {forbidden}")
    if "trabajo.extend(await _procesar_change_value(" not in body:
        raise RuntimeError("change-value delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
