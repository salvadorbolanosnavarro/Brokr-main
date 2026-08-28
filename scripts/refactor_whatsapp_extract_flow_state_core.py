#!/usr/bin/env python3
"""Extract read-only/pure WhatsApp flow-state helpers behind compatibility wrappers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_flow_state.py"
TARGETS = {
    "_flujo_estado_de": "_flujo_estado_de_core",
    "_flujo_menu_texto": "_flujo_menu_texto_core",
}
IMPORT_TEXT = (
    "from routers.whatsapp_flow_state import "
    "_flujo_estado_de_core, _flujo_menu_texto_core\n"
)
WRAPPERS = {
    "_flujo_estado_de": '''async def _flujo_estado_de(conversacion_id: str) -> dict | None:\n    return await _flujo_estado_de_core(conversacion_id, sb_get=sb_get)\n''',
    "_flujo_menu_texto": '''def _flujo_menu_texto(paso: dict) -> str:\n    return _flujo_menu_texto_core(paso)\n''',
}
EXPECTED_KW = {
    "_flujo_estado_de": {"sb_get"},
    "_flujo_menu_texto": set(),
}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing flow-state extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp flow-state helpers are already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = {legacy: _function(source_tree, legacy) for legacy in TARGETS}
    canonical_fns = {legacy: _function(canonical_tree, core) for legacy, core in TARGETS.items()}
    mismatched = [legacy for legacy in TARGETS
                  if _body_shape(source_fns[legacy]) != _body_shape(canonical_fns[legacy])]
    if mismatched:
        raise SystemExit("refusing flow-state extraction: executable bodies differ: " + ", ".join(mismatched))

    lines = source.splitlines(keepends=True)
    replacements = []
    for legacy, node in source_fns.items():
        if node.end_lineno is None:
            raise SystemExit(f"refusing flow-state extraction: {legacy} lacks end_lineno")
        replacements.append((node.lineno, node.end_lineno, WRAPPERS[legacy]))
    for start, end, wrapper in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper, "\n"]

    intermediate = "".join(lines)
    tree = ast.parse(intermediate, filename=str(SOURCE))
    first_wrapper = min(_function(tree, legacy).lineno for legacy in TARGETS)
    current = intermediate.splitlines(keepends=True)
    current[first_wrapper - 1:first_wrapper - 1] = [IMPORT_TEXT, "\n"]
    updated = "".join(current)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    imports = [node for node in updated_tree.body
               if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_flow_state"]
    if len(imports) != 1:
        raise SystemExit("refusing flow-state extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    if names != {(core, None) for core in TARGETS.values()}:
        raise SystemExit(f"refusing flow-state extraction: unexpected import contract {names}")

    for legacy, core in TARGETS.items():
        wrapper = _function(updated_tree, legacy)
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
        if len(calls) != 1:
            raise SystemExit(f"refusing flow-state extraction: {legacy} wrapper call count differs")
        call = calls[0]
        if not isinstance(call.func, ast.Name) or call.func.id != core:
            raise SystemExit(f"refusing flow-state extraction: {legacy} wrong delegate")
        if {kw.arg for kw in call.keywords} != EXPECTED_KW[legacy]:
            raise SystemExit(f"refusing flow-state extraction: {legacy} dependency contract differs")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp flow-state read/pure helpers")


if __name__ == "__main__":
    main()
