#!/usr/bin/env python3
"""Extract pure WhatsApp 2 AI conversation policy from whatsapp.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
IMPORT = "from routers.whatsapp_policy import _conv_pausada, _ia_decide, _modo_conv, _parse_ts\n"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
BLOCK_START = "def _parse_ts(v) -> datetime | None:\n"
BLOCK_END = "async def _pausar_por_respuesta_manual(conv: dict, numero: dict, entren: dict | None = None) -> dict:\n"
NAMES = ("_parse_ts", "_modo_conv", "_conv_pausada", "_ia_decide")


def transform_source(source: str) -> str:
    transformed = source

    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp policy import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if BLOCK_START in transformed:
        start = transformed.index(BLOCK_START)
        end = transformed.find(BLOCK_END, start)
        if end == -1:
            raise RuntimeError("WhatsApp policy block end not found")
        transformed = transformed[:start] + transformed[end:]
    elif any(f"def {name}(" in transformed for name in NAMES):
        raise RuntimeError("Partial WhatsApp policy extraction detected")

    for name in NAMES:
        if f"def {name}(" in transformed:
            raise RuntimeError(f"{name} implementation still present in whatsapp.py")

    if IMPORT not in transformed:
        raise RuntimeError("WhatsApp policy import missing")
    if "async def _pausar_por_respuesta_manual(" not in transformed:
        raise RuntimeError("Manual-pause I/O policy moved unexpectedly")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    SOURCE.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
