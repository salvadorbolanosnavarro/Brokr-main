#!/usr/bin/env python3
"""Extract WhatsApp contact/conversation creation behind compatibility wrappers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_conversation_state.py"
TARGETS = {
    "_get_o_crea_contacto": "_get_o_crea_contacto_core",
    "_get_o_crea_conversacion": "_get_o_crea_conversacion_core",
}
IMPORT_TEXT = (
    "from routers.whatsapp_conversation_state import "
    "_get_o_crea_contacto_core, _get_o_crea_conversacion_core\n"
)
WRAPPERS = {
    "_get_o_crea_contacto": '''async def _get_o_crea_contacto(user_id: str, numero_id: str, wa_id: str, nombre: str | None,\n                               crear_crm: bool = True) -> dict:\n    return await _get_o_crea_contacto_core(\n        user_id,\n        numero_id,\n        wa_id,\n        nombre,\n        crear_crm,\n        sb_get=sb_get,\n        _solo_digitos=_solo_digitos,\n        _crear_contacto_crm=_crear_contacto_crm,\n        sb_post=sb_post,\n        _now=_now,\n    )\n''',
    "_get_o_crea_conversacion": '''async def _get_o_crea_conversacion(user_id: str, numero_id: str, contacto_id: str,\n                                   ia_default: bool = True) -> dict:\n    return await _get_o_crea_conversacion_core(\n        user_id,\n        numero_id,\n        contacto_id,\n        ia_default,\n        sb_get=sb_get,\n        _now=_now,\n        sb_post=sb_post,\n    )\n''',
}
EXPECTED_KW = {
    "_get_o_crea_contacto": {"sb_get", "_solo_digitos", "_crear_contacto_crm", "sb_post", "_now"},
    "_get_o_crea_conversacion": {"sb_get", "_now", "sb_post"},
}


def _function(tree: ast.Module, name: str):
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing conversation-state extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp conversation state is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = {legacy: _function(source_tree, legacy) for legacy in TARGETS}
    canonical_fns = {legacy: _function(canonical_tree, core) for legacy, core in TARGETS.items()}

    mismatched = [
        legacy for legacy in TARGETS
        if _body_shape(source_fns[legacy]) != _body_shape(canonical_fns[legacy])
    ]
    if mismatched:
        raise SystemExit("refusing conversation-state extraction: executable bodies differ: " + ", ".join(mismatched))

    lines = source.splitlines(keepends=True)
    replacements = []
    for legacy, node in source_fns.items():
        if node.end_lineno is None:
            raise SystemExit(f"refusing conversation-state extraction: {legacy} lacks end_lineno")
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

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_conversation_state"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing conversation-state extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    expected_names = {(core, None) for core in TARGETS.values()}
    if names != expected_names:
        raise SystemExit(f"refusing conversation-state extraction: unexpected import contract {names}")

    for legacy, core in TARGETS.items():
        wrapper = _function(updated_tree, legacy)
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
        if len(calls) != 1:
            raise SystemExit(f"refusing conversation-state extraction: {legacy} wrapper has unexpected call count")
        call = calls[0]
        if not isinstance(call.func, ast.Name) or call.func.id != core:
            raise SystemExit(f"refusing conversation-state extraction: {legacy} does not delegate to {core}")
        actual_kw = {kw.arg for kw in call.keywords}
        if actual_kw != EXPECTED_KW[legacy]:
            raise SystemExit(f"refusing conversation-state extraction: {legacy} dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp contact/conversation creation helpers")


if __name__ == "__main__":
    main()
