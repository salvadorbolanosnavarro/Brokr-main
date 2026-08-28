#!/usr/bin/env python3
"""Extract WhatsApp advisor Anthropic orchestration behind a compatibility wrapper."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_advisor_brain.py"
LEGACY = "_broq_asesor"
CORE = "_broq_asesor_core"
IMPORT_TEXT = "from routers.whatsapp_advisor_brain import _broq_asesor_core\n"
WRAPPER = '''async def _broq_asesor(item: dict, numero: dict, user_id: str):\n    return await _broq_asesor_core(\n        item, numero, user_id,\n        _entrenamiento_de=_entrenamiento_de, sb_get=sb_get, HISTORY_LIMIT=HISTORY_LIMIT,\n        _fmt_fecha_larga=_fmt_fecha_larga, _hora_local=_hora_local, httpx=httpx,\n        ANTHROPIC_BASE=ANTHROPIC_BASE, ANTHROPIC_API_KEY=ANTHROPIC_API_KEY, WA2_MODEL=WA2_MODEL,\n        ASESOR_TOOLS=ASESOR_TOOLS, log=log, _asesor_ejecutar_tool=_asesor_ejecutar_tool,\n        _wa_send_text=_wa_send_text, _guardar_mensaje=_guardar_mensaje,\n    )\n'''
EXPECTED_KW = {
    "_entrenamiento_de", "sb_get", "HISTORY_LIMIT", "_fmt_fecha_larga", "_hora_local", "httpx",
    "ANTHROPIC_BASE", "ANTHROPIC_API_KEY", "WA2_MODEL", "ASESOR_TOOLS", "log",
    "_asesor_ejecutar_tool", "_wa_send_text", "_guardar_mensaje",
}


def _function(tree: ast.Module, name: str):
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise SystemExit(f"refusing advisor-brain extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp advisor brain is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _function(source_tree, LEGACY)
    canonical_fn = _function(canonical_tree, CORE)
    if _body_shape(source_fn) != _body_shape(canonical_fn):
        raise SystemExit("refusing advisor-brain extraction: executable bodies differ")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing advisor-brain extraction: missing end_lineno")

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
               if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_advisor_brain"]
    if len(imports) != 1:
        raise SystemExit("refusing advisor-brain extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    if names != {(CORE, None)}:
        raise SystemExit(f"refusing advisor-brain extraction: unexpected import contract {names}")

    wrapper = _function(updated_tree, LEGACY)
    calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    if len(calls) != 1:
        raise SystemExit("refusing advisor-brain extraction: unexpected wrapper call count")
    call = calls[0]
    if not isinstance(call.func, ast.Name) or call.func.id != CORE:
        raise SystemExit("refusing advisor-brain extraction: wrong delegate")
    actual_kw = {kw.arg for kw in call.keywords}
    if actual_kw != EXPECTED_KW:
        raise SystemExit(f"refusing advisor-brain extraction: dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp advisor Anthropic orchestration")


if __name__ == "__main__":
    main()
