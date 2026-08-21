#!/usr/bin/env python3
"""Extract destructive WhatsApp routes into their isolated router.

Static refactor only: this script rewrites source code and never invokes an
endpoint or touches application data.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_delete import router as whatsapp_delete_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_delete_router)\n"
NAMES = {"wa2_numero_delete", "wa2_borrar_mensaje", "wa2_borrar_conversacion"}


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
            start = node.lineno - 1
            # Include decorators in the removed span.
            if node.decorator_list:
                start = min(d.lineno for d in node.decorator_list) - 1
            spans.append((start, node.end_lineno))

    if found and found != NAMES:
        raise RuntimeError(f"partial destructive extraction detected: {sorted(found)}")

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
    if INCLUDE_LINE not in transformed:
        if ROUTER_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp root router anchor not found")
        transformed = transformed.replace(ROUTER_ANCHOR, ROUTER_ANCHOR + INCLUDE_LINE, 1)

    parsed = ast.parse(transformed)
    remaining = {
        node.name for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES
    }
    if remaining:
        raise RuntimeError(f"destructive WhatsApp handlers remain: {sorted(remaining)}")

    # Other mutation/deletion domains are explicitly outside this cut.
    if "async def wa2_automatizacion_delete" not in transformed:
        raise RuntimeError("automation deletion moved unexpectedly")
    if "async def _borrar_archivos" not in transformed:
        # Compatible with the media-storage extraction being applied first.
        if "borrar_archivos as _borrar_archivos" not in transformed:
            raise RuntimeError("media deletion helper missing unexpectedly")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
