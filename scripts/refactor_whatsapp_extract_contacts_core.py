#!/usr/bin/env python3
"""Extract WhatsApp number/agenda/contact/conversation persistence helpers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_contacts import (\n"
    "    agenda_upsert as _agenda_upsert, get_numero as _get_numero,\n"
    "    get_o_crea_contacto as _get_o_crea_contacto,\n"
    "    get_o_crea_conversacion as _get_o_crea_conversacion,\n"
    ")\n"
)
REMOVE = {"_get_numero", "_agenda_upsert", "_get_o_crea_contacto", "_get_o_crea_conversacion"}


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
    for forbidden in (
        "async def _get_numero",
        "async def _agenda_upsert",
        "async def _get_o_crea_contacto",
        "async def _get_o_crea_conversacion",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"contact persistence implementation remains: {forbidden}")
    for required in (
        "numero = await _get_numero(phone_number_id)",
        "await _agenda_upsert(",
        "await _get_o_crea_contacto(",
        "await _get_o_crea_conversacion(",
        "async def _persistir_entrantes",
    ):
        if required not in transformed:
            raise RuntimeError(f"contact persistence caller missing: {required}")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
