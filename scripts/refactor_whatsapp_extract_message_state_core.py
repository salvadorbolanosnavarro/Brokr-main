#!/usr/bin/env python3
"""Extract WhatsApp message persistence/property resolver behind wrappers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_message_state.py"
TARGETS = {
    "_guardar_mensaje": "_guardar_mensaje_core",
    "_resolver_inmueble_id": "_resolver_inmueble_id_core",
}
IMPORT_TEXT = (
    "from routers.whatsapp_message_state import "
    "_guardar_mensaje_core, _resolver_inmueble_id_core\n"
)
WRAPPERS = {
    "_guardar_mensaje": '''async def _guardar_mensaje(user_id: str, contacto_id: str, conversacion_id: str, wamid: str | None,\n                          direction: str, sender: str, body: str, media_url: str | None = None,\n                          media_path: str | None = None) -> None:\n    return await _guardar_mensaje_core(\n        user_id, contacto_id, conversacion_id, wamid, direction, sender, body, media_url, media_path,\n        _now=_now, sb_post=sb_post, sb_get=sb_get, log=log, sb_patch=sb_patch,\n    )\n''',
    "_resolver_inmueble_id": '''def _resolver_inmueble_id(inmueble_txt: str, ultimas: list) -> str | None:\n    return _resolver_inmueble_id_core(inmueble_txt, ultimas)\n''',
}
EXPECTED_KW = {
    "_guardar_mensaje": {"_now", "sb_post", "sb_get", "log", "sb_patch"},
    "_resolver_inmueble_id": set(),
}


def _function(tree: ast.Module, name: str):
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing message-state extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp message state is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = {legacy: _function(source_tree, legacy) for legacy in TARGETS}
    canonical_fns = {legacy: _function(canonical_tree, core) for legacy, core in TARGETS.items()}

    mismatched = [
        legacy for legacy in TARGETS
        if _body_shape(source_fns[legacy]) != _body_shape(canonical_fns[legacy])
    ]
    if mismatched:
        raise SystemExit("refusing message-state extraction: executable bodies differ: " + ", ".join(mismatched))

    lines = source.splitlines(keepends=True)
    replacements = []
    for legacy, node in source_fns.items():
        if node.end_lineno is None:
            raise SystemExit(f"refusing message-state extraction: {legacy} lacks end_lineno")
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
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_message_state"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing message-state extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    expected_names = {(core, None) for core in TARGETS.values()}
    if names != expected_names:
        raise SystemExit(f"refusing message-state extraction: unexpected import contract {names}")

    for legacy, core in TARGETS.items():
        wrapper = _function(updated_tree, legacy)
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
        if len(calls) != 1:
            raise SystemExit(f"refusing message-state extraction: {legacy} wrapper has unexpected call count")
        call = calls[0]
        if not isinstance(call.func, ast.Name) or call.func.id != core:
            raise SystemExit(f"refusing message-state extraction: {legacy} does not delegate to {core}")
        actual_kw = {kw.arg for kw in call.keywords}
        if actual_kw != EXPECTED_KW[legacy]:
            raise SystemExit(f"refusing message-state extraction: {legacy} dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp message persistence and property resolver")


if __name__ == "__main__":
    main()
