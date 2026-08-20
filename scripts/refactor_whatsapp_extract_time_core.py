#!/usr/bin/env python3
"""Extract pure WhatsApp 2 time/calendar helpers from whatsapp.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
IMPORT = (
    "from routers.whatsapp_time import (\n"
    "    construir_ics as _construir_ics,\n"
    "    fecha_hora_utc_iso as _fecha_hora_utc_iso,\n"
    "    fmt_fecha_larga as _fmt_fecha_larga,\n"
    "    hora_local as _hora_local,\n"
    "    now_iso as _now,\n"
    ")\n"
)
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
NAMES = {"_now", "_hora_local", "_fmt_fecha_larga", "_fecha_hora_utc_iso", "_construir_ics"}


def transform_source(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    found = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES:
            if node.end_lineno is None:
                raise RuntimeError(f"Missing end line for {node.name}")
            found.add(node.name)
            spans.append((node.lineno - 1, node.end_lineno))

    if found and found != NAMES:
        raise RuntimeError(f"Partial WhatsApp time extraction detected: {sorted(found)}")

    transformed = source
    if found == NAMES:
        for start, end in sorted(spans, reverse=True):
            del lines[start:end]
        transformed = "".join(lines)

    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    parsed = ast.parse(transformed)
    remaining = {
        node.name for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES
    }
    if remaining:
        raise RuntimeError(f"WhatsApp time helpers remain: {sorted(remaining)}")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    SOURCE.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
