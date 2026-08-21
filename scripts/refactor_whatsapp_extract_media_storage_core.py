#!/usr/bin/env python3
"""Extract Storage-backed WhatsApp media persistence helpers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_media_storage import (\n"
    "    borrar_archivos as _borrar_archivos, guardar_archivo as _guardar_archivo,\n"
    ")\n"
)
NAMES = {"_guardar_archivo", "_borrar_archivos"}


def transform_source(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES:
            if node.end_lineno is None:
                raise RuntimeError(f"missing end line for {node.name}")
            found.add(node.name)
            spans.append((node.lineno - 1, node.end_lineno))
    if found and found != NAMES:
        raise RuntimeError(f"partial media-storage extraction: {sorted(found)}")

    if found == NAMES:
        for start, end in sorted(spans, reverse=True):
            del lines[start:end]
        transformed = "".join(lines)
    else:
        transformed = source

    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    parsed = ast.parse(transformed)
    remaining = {
        node.name for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES
    }
    if remaining:
        raise RuntimeError(f"media storage helpers remain: {sorted(remaining)}")

    # Cloud media download/transcription and destructive endpoints remain out of scope.
    for required in (
        "async def _descargar_media",
        "async def _transcribir_audio",
        "async def wa2_borrar_mensaje",
        "async def wa2_borrar_conversacion",
        "async def wa2_numero_delete",
    ):
        if required not in transformed:
            raise RuntimeError(f"out-of-scope WhatsApp behavior moved: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
