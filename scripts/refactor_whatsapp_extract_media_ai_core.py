#!/usr/bin/env python3
"""Extract WhatsApp voice/image AI processing from the root monolith."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_media_ai import (\n"
    "    describir_imagen as _describir_imagen, transcribir_audio as _transcribir_audio,\n"
    ")\n"
)
REMOVE = {"_transcribir_audio", "_describir_imagen"}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    for node in tree.body:
        if getattr(node, "name", None) not in REMOVE:
            continue
        start = node.lineno - 1
        end = node.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)
    transformed = _remove_nodes(transformed)
    for forbidden in ("async def _transcribir_audio", "async def _describir_imagen"):
        if forbidden in transformed:
            raise RuntimeError(f"AI media implementation remains: {forbidden}")
    for required in (
        "await _transcribir_audio(media_bytes, media_mime)",
        "await _describir_imagen(media_bytes, media_mime)",
        "async def _persistir_entrantes",
    ):
        if required not in transformed:
            raise RuntimeError(f"AI media caller missing: {required}")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
