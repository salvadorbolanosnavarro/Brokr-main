#!/usr/bin/env python3
"""Extract WhatsApp advisor context persistence behind a compatibility wrapper."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_advisor_context.py"
LEGACY = "_asesor_ctx_guardar"
CORE = "_asesor_ctx_guardar_core"
IMPORT_TEXT = "from routers.whatsapp_advisor_context import _asesor_ctx_guardar_core\n"
WRAPPER = '''async def _asesor_ctx_guardar(conversacion_id: str, cambios: dict) -> None:\n    return await _asesor_ctx_guardar_core(\n        conversacion_id, cambios, sb_get=sb_get, sb_patch=sb_patch, log=log\n    )\n'''
EXPECTED_KW = {"sb_get", "sb_patch", "log"}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing advisor-context extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp advisor context is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _function(source_tree, LEGACY)
    canonical_fn = _function(canonical_tree, CORE)
    if _body_shape(source_fn) != _body_shape(canonical_fn):
        raise SystemExit("refusing advisor-context extraction: executable bodies differ")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing advisor-context extraction: missing end_lineno")

    lines = source.splitlines(keepends=True)
    lines[source_fn.lineno - 1:source_fn.end_lineno] = [WRAPPER, "\n"]
    intermediate = "".join(lines)
    tree = ast.parse(intermediate, filename=str(SOURCE))
    wrapper = _function(tree, LEGACY)
    current = intermediate.splitlines(keepends=True)
    current[wrapper.lineno - 1:wrapper.lineno - 1] = [IMPORT_TEXT, "\n"]
    updated = "".join(current)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    imports = [node for node in updated_tree.body
               if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_advisor_context"]
    if len(imports) != 1:
        raise SystemExit("refusing advisor-context extraction: expected one canonical import")
    wrapper = _function(updated_tree, LEGACY)
    calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    if len(calls) != 1:
        raise SystemExit("refusing advisor-context extraction: unexpected wrapper call count")
    call = calls[0]
    if not isinstance(call.func, ast.Name) or call.func.id != CORE:
        raise SystemExit("refusing advisor-context extraction: wrong delegate")
    if {kw.arg for kw in call.keywords} != EXPECTED_KW:
        raise SystemExit("refusing advisor-context extraction: dependency contract differs")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp advisor context persistence")


if __name__ == "__main__":
    main()
