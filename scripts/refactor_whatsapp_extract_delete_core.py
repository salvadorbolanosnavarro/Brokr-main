#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_delete_core.py"
IMPORT_MODULE = "routers.whatsapp_delete_core"
SPECS = {
    "wa2_borrar_mensaje": (
        "wa2_borrar_mensaje_core",
        '''async def wa2_borrar_mensaje(mensaje_id: str, request: Request):\n    return await wa2_borrar_mensaje_core(\n        mensaje_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n        _borrar_archivos=_borrar_archivos, sb_delete=sb_delete,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "_borrar_archivos", "sb_delete"},
    ),
    "wa2_borrar_conversacion": (
        "wa2_borrar_conversacion_core",
        '''async def wa2_borrar_conversacion(conversacion_id: str, request: Request):\n    return await wa2_borrar_conversacion_core(\n        conversacion_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n        _borrar_archivos=_borrar_archivos, sb_delete=sb_delete, log=log,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "_borrar_archivos", "sb_delete", "log"},
    ),
}


def fn(tree: ast.Module, name: str):
    xs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(xs) != 1:
        raise SystemExit(f"expected one {name}, found {len(xs)}")
    return xs[0]


def shape(node):
    m = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(m)
    return ast.dump(m, annotate_fields=True, include_attributes=False)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    canon = ast.parse(CANONICAL.read_text(encoding="utf-8"))
    replacements = []
    for legacy_name, (core_name, wrapper_text, _) in SPECS.items():
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if shape(legacy) != shape(core):
            raise SystemExit(f"delete core body differs: {legacy_name}")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper_text))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper_text in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("delete cores already imported")

    nodes = [fn(t2, name) for name in SPECS]
    first = min(min([d.lineno for d in n.decorator_list] or [n.lineno]) for n in nodes)
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_delete_core import (\n"
        "    wa2_borrar_mensaje_core, wa2_borrar_conversacion_core,\n"
        ")\n\n"
    )
    cur[first - 1:first - 1] = [import_text]
    out = "".join(cur)
    t3 = ast.parse(out)
    for legacy_name, (core_name, _, expected) in SPECS.items():
        wrapper = fn(t3, legacy_name)
        calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == core_name]
        if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
            raise SystemExit(f"delete core wrapper contract differs: {legacy_name}")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
