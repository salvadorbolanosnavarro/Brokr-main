#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_automation_write.py"
IMPORT_MODULE = "routers.whatsapp_automation_write"

SPECS = {
    "wa2_automatizaciones_list": (
        "wa2_automatizaciones_list_core",
        '''async def wa2_automatizaciones_list(request: Request):\n    return await wa2_automatizaciones_list_core(\n        request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter"},
    ),
    "wa2_automatizacion_crear": (
        "wa2_automatizacion_crear_core",
        '''async def wa2_automatizacion_crear(req: AutomatizacionReq, request: Request):\n    return await wa2_automatizacion_crear_core(\n        req, request, _require_user=_require_user,\n        _limpiar_automatizacion=_limpiar_automatizacion, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n        _now=_now, sb_post=sb_post,\n    )\n''',
        {"_require_user", "_limpiar_automatizacion", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "_now", "sb_post"},
    ),
    "wa2_automatizacion_patch": (
        "wa2_automatizacion_patch_core",
        '''async def wa2_automatizacion_patch(auto_id: str, request: Request):\n    return await wa2_automatizacion_patch_core(\n        auto_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        _in_filter=_in_filter, sb_get=sb_get, HTTPException=HTTPException,\n        AutomatizacionReq=AutomatizacionReq, _limpiar_automatizacion=_limpiar_automatizacion,\n        _now=_now, sb_patch=sb_patch,\n    )\n''',
        {"_require_user", "_ids_visibles", "_in_filter", "sb_get", "HTTPException", "AutomatizacionReq", "_limpiar_automatizacion", "_now", "sb_patch"},
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
    decorator_starts = []
    for legacy_name, (core_name, wrapper_text, _) in SPECS.items():
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if shape(legacy) != shape(core):
            raise SystemExit(f"automation write body differs: {legacy_name}")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper_text))
        decorator_starts.append(min([d.lineno for d in legacy.decorator_list] or [legacy.lineno]))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper_text in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("automation write already imported")

    first_name = min(SPECS, key=lambda name: min([d.lineno for d in fn(t2, name).decorator_list] or [fn(t2, name).lineno]))
    first_node = fn(t2, first_name)
    first = min([d.lineno for d in first_node.decorator_list] or [first_node.lineno])
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_automation_write import (\n"
        "    wa2_automatizaciones_list_core, wa2_automatizacion_crear_core,\n"
        "    wa2_automatizacion_patch_core,\n"
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
            raise SystemExit(f"automation write wrapper contract differs: {legacy_name}")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
