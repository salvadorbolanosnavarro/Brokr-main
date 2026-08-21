#!/usr/bin/env python3
"""Replace inline coexistence handling with the shared WhatsApp service."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_coexistence import procesar_coexistencia as _procesar_coexistencia\n"
START = "            # ── COEXISTENCIA: ecos de lo que el asesor manda DESDE SU CELULAR ──\n"
END = '            for msg in val.get("messages", []):\n'
REPLACEMENT = (
    "            await _procesar_coexistencia(val, numero)\n\n"
)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "await _procesar_coexistencia(val, numero)" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("coexistence block start not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("incoming-message loop anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    for forbidden in (
        'for eco in (val.get("message_echoes") or []):',
        'for sync in (val.get("state_sync") or []):',
        'for bloque_h in (val.get("history") or []):',
    ):
        if forbidden in transformed:
            raise RuntimeError(f"inline coexistence branch remains: {forbidden}")
    if "await _procesar_coexistencia(val, numero)" not in transformed:
        raise RuntimeError("coexistence delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
