#!/usr/bin/env python3
"""Extract WhatsApp agenda/identity helpers behind compatibility wrappers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_agenda.py"
TARGETS = {
    "_solo_digitos": "_solo_digitos_core",
    "_es_asesor": "_es_asesor_core",
    "_agenda_upsert": "_agenda_upsert_core",
}
IMPORT_TEXT = (
    "from routers.whatsapp_agenda import "
    "_agenda_upsert_core, _es_asesor_core, _solo_digitos_core\n"
)
WRAPPERS = {
    "_solo_digitos": '''def _solo_digitos(t: str) -> str:\n    return _solo_digitos_core(t, re=re)\n''',
    "_es_asesor": '''def _es_asesor(numero: dict, wa_id: str) -> bool:\n    return _es_asesor_core(numero, wa_id, _normaliza_mx=_normaliza_mx)\n''',
    "_agenda_upsert": '''async def _agenda_upsert(user_id: str, numero_id: str, telefono: str,\n                         nombre: str | None = None, conocido: bool | None = None) -> None:\n    return await _agenda_upsert_core(\n        user_id,\n        numero_id,\n        telefono,\n        nombre,\n        conocido,\n        sb_get=sb_get,\n        _now=_now,\n        sb_patch=sb_patch,\n        sb_post=sb_post,\n        log=log,\n    )\n''',
}
EXPECTED_KW = {
    "_solo_digitos": {"re"},
    "_es_asesor": {"_normaliza_mx"},
    "_agenda_upsert": {"sb_get", "_now", "sb_patch", "sb_post", "log"},
}


def _function(tree: ast.Module, name: str):
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing agenda extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp agenda identity is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = {legacy: _function(source_tree, legacy) for legacy in TARGETS}
    canonical_fns = {legacy: _function(canonical_tree, core) for legacy, core in TARGETS.items()}

    mismatched = [
        legacy for legacy in TARGETS
        if _body_shape(source_fns[legacy]) != _body_shape(canonical_fns[legacy])
    ]
    if mismatched:
        raise SystemExit("refusing agenda extraction: executable bodies differ: " + ", ".join(mismatched))

    lines = source.splitlines(keepends=True)
    replacements = []
    for legacy, node in source_fns.items():
        if node.end_lineno is None:
            raise SystemExit(f"refusing agenda extraction: {legacy} lacks end_lineno")
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
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_agenda"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing agenda extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    expected_names = {(core, None) for core in TARGETS.values()}
    if names != expected_names:
        raise SystemExit(f"refusing agenda extraction: unexpected import contract {names}")

    for legacy, core in TARGETS.items():
        wrapper = _function(updated_tree, legacy)
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
        if len(calls) != 1:
            raise SystemExit(f"refusing agenda extraction: {legacy} wrapper has unexpected call count")
        call = calls[0]
        if not isinstance(call.func, ast.Name) or call.func.id != core:
            raise SystemExit(f"refusing agenda extraction: {legacy} does not delegate to {core}")
        actual_kw = {kw.arg for kw in call.keywords}
        if actual_kw != EXPECTED_KW[legacy]:
            raise SystemExit(f"refusing agenda extraction: {legacy} dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp agenda and advisor identity helpers")


if __name__ == "__main__":
    main()
