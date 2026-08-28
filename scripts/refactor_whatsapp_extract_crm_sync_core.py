#!/usr/bin/env python3
"""Extract WhatsApp CRM contact creation/sync behind compatibility wrappers."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_crm_sync.py"
TARGETS = {
    "_crear_contacto_crm": "_crear_contacto_crm_core",
    "_sincronizar_contacto_crm": "_sincronizar_contacto_crm_core",
}
IMPORT_TEXT = (
    "from routers.whatsapp_crm_sync import "
    "_crear_contacto_crm_core, _sincronizar_contacto_crm_core\n"
)
WRAPPERS = {
    "_crear_contacto_crm": '''async def _crear_contacto_crm(user_id: str, wa_id: str, nombre: str | None) -> str | None:\n    return await _crear_contacto_crm_core(\n        user_id,\n        wa_id,\n        nombre,\n        datetime=datetime,\n        timezone=timezone,\n        _normaliza_mx=_normaliza_mx,\n        get_org_context=get_org_context,\n        _now=_now,\n        sb_post=sb_post,\n        log=log,\n    )\n''',
    "_sincronizar_contacto_crm": '''async def _sincronizar_contacto_crm(user_id: str, contacto_wa2: dict, resultado_ia: dict | None = None) -> None:\n    return await _sincronizar_contacto_crm_core(\n        user_id,\n        contacto_wa2,\n        resultado_ia,\n        _now=_now,\n        sb_get=sb_get,\n        _hora_local=_hora_local,\n        sb_patch=sb_patch,\n        log=log,\n    )\n''',
}
EXPECTED_KW = {
    "_crear_contacto_crm": {
        "datetime", "timezone", "_normaliza_mx", "get_org_context", "_now", "sb_post", "log",
    },
    "_sincronizar_contacto_crm": {"_now", "sb_get", "_hora_local", "sb_patch", "log"},
}


def _function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing CRM-sync extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _body_shape(node: ast.AsyncFunctionDef) -> str:
    module = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.dump(module, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp CRM sync is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fns = {legacy: _function(source_tree, legacy) for legacy in TARGETS}
    canonical_fns = {legacy: _function(canonical_tree, core) for legacy, core in TARGETS.items()}

    mismatched = [
        legacy for legacy in TARGETS
        if _body_shape(source_fns[legacy]) != _body_shape(canonical_fns[legacy])
    ]
    if mismatched:
        raise SystemExit("refusing CRM-sync extraction: executable bodies differ: " + ", ".join(mismatched))

    lines = source.splitlines(keepends=True)
    replacements = []
    for legacy, node in source_fns.items():
        if node.end_lineno is None:
            raise SystemExit(f"refusing CRM-sync extraction: {legacy} lacks end_lineno")
        replacements.append((node.lineno, node.end_lineno, WRAPPERS[legacy]))

    # Replace bottom-up so original line coordinates remain valid.
    for start, end, wrapper in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper, "\n"]

    # Place canonical import immediately before the first wrapper.
    first_line = min(start for start, _, _ in replacements)
    # Reparse after replacements to find the first wrapper's current line reliably.
    intermediate = "".join(lines)
    intermediate_tree = ast.parse(intermediate, filename=str(SOURCE))
    first_wrapper = min(_function(intermediate_tree, legacy).lineno for legacy in TARGETS)
    current_lines = intermediate.splitlines(keepends=True)
    current_lines[first_wrapper - 1:first_wrapper - 1] = [IMPORT_TEXT, "\n"]
    updated = "".join(current_lines)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_crm_sync"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing CRM-sync extraction: expected one canonical import")
    names = {(alias.name, alias.asname) for alias in imports[0].names}
    expected_names = {(core, None) for core in TARGETS.values()}
    if names != expected_names:
        raise SystemExit(f"refusing CRM-sync extraction: unexpected import contract {names}")

    for legacy, core in TARGETS.items():
        wrapper = _function(updated_tree, legacy)
        calls = [node for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
        if len(calls) != 1:
            raise SystemExit(f"refusing CRM-sync extraction: {legacy} wrapper has unexpected call count")
        call = calls[0]
        if not isinstance(call.func, ast.Name) or call.func.id != core:
            raise SystemExit(f"refusing CRM-sync extraction: {legacy} does not delegate to {core}")
        actual_kw = {kw.arg for kw in call.keywords}
        if actual_kw != EXPECTED_KW[legacy]:
            raise SystemExit(f"refusing CRM-sync extraction: {legacy} dependency contract differs {actual_kw}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp CRM contact creation and synchronization")


if __name__ == "__main__":
    main()
