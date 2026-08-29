#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_campaign_read.py"
IMPORT_MODULE = "routers.whatsapp_campaign_read"
SPECS = {
    "wa2_etiquetas_list": (
        "wa2_etiquetas_list_core",
        '''async def wa2_etiquetas_list(request: Request):\n    return await wa2_etiquetas_list_core(\n        request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter"},
    ),
    "wa2_campanas_list": (
        "wa2_campanas_list_core",
        '''async def wa2_campanas_list(request: Request):\n    return await wa2_campanas_list_core(\n        request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter"},
    ),
    "wa2_campana_detalle": (
        "wa2_campana_detalle_core",
        '''async def wa2_campana_detalle(campana_id: str, request: Request):\n    return await wa2_campana_detalle_core(\n        campana_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException"},
    ),
}


def fn(tree, name):
    xs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(xs) != 1:
        raise SystemExit(f"expected one {name}, found {len(xs)}")
    return xs[0]


def shape(node):
    m = ast.Module(body=node.body, type_ignores=[])
    ast.fix_missing_locations(m)
    return ast.dump(m, annotate_fields=True, include_attributes=False)


def start_line(node):
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def main():
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    canon = ast.parse(CANONICAL.read_text(encoding="utf-8"))

    replacements = []
    for legacy_name, (core_name, wrapper_text, _) in SPECS.items():
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if shape(legacy) != shape(core):
            raise SystemExit(f"campaign read body differs: {legacy_name}")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper_text))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper_text in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("campaign read already imported")

    first = min(start_line(fn(t2, name)) for name in SPECS)
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_campaign_read import (\n"
        "    wa2_etiquetas_list_core, wa2_campanas_list_core, wa2_campana_detalle_core,\n"
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
            raise SystemExit(f"campaign read wrapper contract differs: {legacy_name}")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
