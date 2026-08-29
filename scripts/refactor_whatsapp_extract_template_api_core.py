#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_template_api.py"
SPECS = (
    (
        "wa2_plantillas_list", "wa2_plantillas_list_core",
        '''async def wa2_plantillas_list(request: Request, numero_id: str):\n    return await wa2_plantillas_list_core(\n        request, numero_id, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n        httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "httpx", "GRAPH_API", "log"},
    ),
    (
        "wa2_plantilla_crear", "wa2_plantilla_crear_core",
        '''async def wa2_plantilla_crear(req: PlantillaCrearReq, request: Request):\n    return await wa2_plantilla_crear_core(\n        req, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException, re=re,\n        httpx=httpx, GRAPH_API=GRAPH_API, log=log,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "re", "httpx", "GRAPH_API", "log"},
    ),
    (
        "wa2_enviar_plantilla", "wa2_enviar_plantilla_core",
        '''async def wa2_enviar_plantilla(req: PlantillaEnviarReq, request: Request):\n    return await wa2_enviar_plantilla_core(\n        req, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n        httpx=httpx, GRAPH_API=GRAPH_API, log=log, _guardar_mensaje=_guardar_mensaje,\n    )\n''',
        {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "httpx", "GRAPH_API", "log", "_guardar_mensaje"},
    ),
)


def fn(tree, name):
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
    for legacy_name, core_name, wrapper, _expected in SPECS:
        legacy = fn(tree, legacy_name)
        core = fn(canon, core_name)
        if shape(legacy) != shape(core):
            raise SystemExit(f"{legacy_name} body differs")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_template_api" for n in t2.body):
        raise SystemExit("template API already imported")

    first = fn(t2, SPECS[0][0])
    insert_line = min([d.lineno for d in first.decorator_list] or [first.lineno])
    cur = mid.splitlines(keepends=True)
    cur[insert_line - 1:insert_line - 1] = [
        "from routers.whatsapp_template_api import (wa2_plantillas_list_core, wa2_plantilla_crear_core, wa2_enviar_plantilla_core)\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    for legacy_name, core_name, _wrapper, expected in SPECS:
        wrapper_node = fn(t3, legacy_name)
        calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == core_name]
        if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
            raise SystemExit(f"{legacy_name} wrapper contract differs")
        if not wrapper_node.decorator_list:
            raise SystemExit(f"{legacy_name} route decorator lost")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
