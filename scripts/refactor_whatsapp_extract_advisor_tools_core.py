#!/usr/bin/env python3
"""Extract WhatsApp advisor DB tool execution behind a compatibility wrapper."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_advisor_tools.py"
LEGACY = "_asesor_ejecutar_tool"
CORE = "_asesor_ejecutar_tool_core"
IMPORT_TEXT = "from routers.whatsapp_advisor_tools import _asesor_ejecutar_tool_core\n"
WRAPPER = '''async def _asesor_ejecutar_tool(user_id: str, name: str, args: dict, zona: str | None,\n                                conversacion_id: str) -> str:\n    return await _asesor_ejecutar_tool_core(\n        user_id, name, args, zona, conversacion_id,\n        sb_get=sb_get, _hora_local=_hora_local, _now=_now, sb_patch=sb_patch,\n        _asesor_ctx_guardar=_asesor_ctx_guardar, _fecha_hora_utc_iso=_fecha_hora_utc_iso,\n        sb_post=sb_post,\n    )\n'''
EXPECTED_KW = {"sb_get", "_hora_local", "_now", "sb_patch", "_asesor_ctx_guardar", "_fecha_hora_utc_iso", "sb_post"}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing advisor-tools extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp advisor tools are already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _function(source_tree, LEGACY)
    canonical_fn = _function(canonical_tree, CORE)
    if _body_shape(source_fn) != _body_shape(canonical_fn):
        raise SystemExit("refusing advisor-tools extraction: executable bodies differ")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing advisor-tools extraction: missing end_lineno")

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
               if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_advisor_tools"]
    if len(imports) != 1:
        raise SystemExit("refusing advisor-tools extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    if names != {(CORE, None)}:
        raise SystemExit(f"refusing advisor-tools extraction: unexpected import contract {names}")

    wrapper = _function(updated_tree, LEGACY)
    calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    if len(calls) != 1:
        raise SystemExit("refusing advisor-tools extraction: unexpected wrapper call count")
    call = calls[0]
    if not isinstance(call.func, ast.Name) or call.func.id != CORE:
        raise SystemExit("refusing advisor-tools extraction: wrong delegate")
    actual_kw = {kw.arg for kw in call.keywords}
    if actual_kw != EXPECTED_KW:
        raise SystemExit(f"refusing advisor-tools extraction: dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp advisor DB tool execution")


if __name__ == "__main__":
    main()
