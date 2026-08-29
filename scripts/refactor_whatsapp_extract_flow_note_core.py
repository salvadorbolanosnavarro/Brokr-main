#!/usr/bin/env python3
"""Extract WhatsApp flow final-note helper behind a compatibility wrapper."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_flow_state.py"
LEGACY = "_flujo_nota_final"
CORE = "_flujo_nota_final_core"
IMPORT_MODULE = "routers.whatsapp_flow_state"
WRAPPER = '''async def _flujo_nota_final(user_id: str, contacto_id: str, auto_nombre: str, datos: dict) -> None:\n    return await _flujo_nota_final_core(\n        user_id, contacto_id, auto_nombre, datos,\n        sb_get=sb_get, _now=_now, sb_patch=sb_patch,\n        _sincronizar_contacto_crm=_sincronizar_contacto_crm, log=log,\n    )\n'''
EXPECTED_KW = {"sb_get", "_now", "sb_patch", "_sincronizar_contacto_crm", "log"}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing flow-note extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))

    legacy = _function(source_tree, LEGACY)
    core = _function(canonical_tree, CORE)
    if _body_shape(legacy) != _body_shape(core):
        raise SystemExit("refusing flow-note extraction: executable bodies differ")

    lines = source.splitlines(keepends=True)
    if legacy.end_lineno is None:
        raise SystemExit("refusing flow-note extraction: legacy helper lacks end_lineno")
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    intermediate = "".join(lines)

    tree = ast.parse(intermediate, filename=str(SOURCE))
    imports = [node for node in tree.body
               if isinstance(node, ast.ImportFrom) and node.module == IMPORT_MODULE]
    if len(imports) != 1:
        raise SystemExit("refusing flow-note extraction: expected one existing flow-state import")
    imp = imports[0]
    names = [alias.name for alias in imp.names]
    if CORE in names:
        raise SystemExit("WhatsApp flow final-note helper is already extracted")
    import_text = "from routers.whatsapp_flow_state import " + ", ".join(names + [CORE]) + "\n"

    current = intermediate.splitlines(keepends=True)
    if imp.end_lineno is None:
        raise SystemExit("refusing flow-note extraction: import lacks end_lineno")
    current[imp.lineno - 1:imp.end_lineno] = [import_text]
    updated = "".join(current)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    wrapper = _function(updated_tree, LEGACY)
    calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    delegate = [call for call in calls if isinstance(call.func, ast.Name) and call.func.id == CORE]
    if len(delegate) != 1:
        raise SystemExit("refusing flow-note extraction: wrapper delegate count differs")
    if {kw.arg for kw in delegate[0].keywords} != EXPECTED_KW:
        raise SystemExit("refusing flow-note extraction: dependency contract differs")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp flow final-note helper")


if __name__ == "__main__":
    main()
