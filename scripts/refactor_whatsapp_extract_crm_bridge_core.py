#!/usr/bin/env python3
"""Extract WhatsApp agent-profile and CRM contact bridge helpers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_crm_bridge import (\n"
    "    crear_contacto_crm as _crear_contacto_crm, perfil_agente as _perfil_agente,\n"
    "    sincronizar_contacto_crm as _sincronizar_contacto_crm,\n"
    ")\n"
)
REMOVE = {"_perfil_agente", "_crear_contacto_crm", "_sincronizar_contacto_crm"}


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

    for forbidden in (
        "async def _perfil_agente",
        "async def _crear_contacto_crm",
        "async def _sincronizar_contacto_crm",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"CRM bridge implementation remains: {forbidden}")
    for required in (
        "agente = await _perfil_agente(dueño)",
        "await _crear_contacto_crm(user_id, wa_id, display)",
        "await _sincronizar_contacto_crm(user_id, dict(contacto, **update_contacto), resultado)",
        "await _sincronizar_contacto_crm(user_id, rows[0], {\"nota\": req.texto})",
    ):
        if required not in transformed:
            raise RuntimeError(f"CRM bridge caller missing: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
