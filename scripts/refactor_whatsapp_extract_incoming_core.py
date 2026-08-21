#!/usr/bin/env python3
"""Replace the inline inbound-message loop with the shared persistence service."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_incoming import persistir_mensaje_entrante as _persistir_mensaje_entrante\n"
)
START = '            for msg in val.get("messages", []):\n'
END = "            # ── Acuses de Meta (enviado / entregado / leído / FALLIDO) ──────\n"
REPLACEMENT = (
    '            for msg in val.get("messages", []):\n'
    '                item = await _persistir_mensaje_entrante(msg, numero, contactos_meta)\n'
    '                if item:\n'
    '                    trabajo.append(item)\n\n'
)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "item = await _persistir_mensaje_entrante(msg, numero, contactos_meta)" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("incoming-message loop start not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("delivery-status anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    for forbidden in (
        "Mensaje anterior a la conexión del número",
        'wa_message_id": f"eq.{msg.get(\'id\')}"',
        "OPT_OUT_PALABRAS",
        "_OPT_OUT_PALABRAS",
    ):
        # Constants/comments elsewhere are allowed; only inspect the remaining
        # persistir_entrantes body before delivery-status handling.
        body_start = transformed.find("async def _persistir_entrantes")
        body_end = transformed.find(END, body_start)
        if body_start != -1 and body_end != -1 and forbidden in transformed[body_start:body_end]:
            raise RuntimeError(f"inline incoming concern remains: {forbidden}")
    if "item = await _persistir_mensaje_entrante(msg, numero, contactos_meta)" not in transformed:
        raise RuntimeError("incoming-message delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
