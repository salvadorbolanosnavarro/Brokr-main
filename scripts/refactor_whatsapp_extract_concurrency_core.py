#!/usr/bin/env python3
"""Extract the bounded per-conversation lock registry from whatsapp.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_concurrency import lock_conv as _lock_conv\n"


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    found_lock = False
    found_registry = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_lock_conv":
            found_lock = True
            start, end = node.lineno - 1, node.end_lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_LOCKS":
            found_registry = True
            start, end = node.lineno - 1, node.end_lineno
        else:
            continue
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
    if not found_lock or not found_registry:
        raise RuntimeError("WhatsApp lock registry/function not found")
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "def _lock_conv(" not in transformed and "_LOCKS: dict" not in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    transformed = _remove_nodes(transformed)
    if "def _lock_conv(" in transformed or "_LOCKS: dict" in transformed:
        raise RuntimeError("WhatsApp lock implementation remains in root")
    if "async with _lock_conv(item[\"conversacion_id\"]):" not in transformed:
        raise RuntimeError("WhatsApp lock caller changed unexpectedly")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
