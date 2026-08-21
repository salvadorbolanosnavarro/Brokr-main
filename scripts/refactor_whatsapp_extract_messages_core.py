#!/usr/bin/env python3
"""Extract shared WhatsApp message persistence from the root monolith."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_messages import guardar_mensaje as _guardar_mensaje\n"
REMOVE = {"_guardar_mensaje"}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    for node in tree.body:
        if getattr(node, "name", None) not in REMOVE:
            continue
        start = node.lineno - 1
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(d.lineno for d in decorators) - 1
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

    if "async def _guardar_mensaje" in transformed:
        raise RuntimeError("message persistence implementation remains")
    for required in (
        "await _guardar_mensaje(",
        "async def _persistir_entrantes",
        "async def _correr_campana",
        "async def _procesar_en_segundo_plano",
    ):
        if required not in transformed:
            raise RuntimeError(f"message persistence caller missing: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
