#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_automation_delete.py"
LEGACY = "wa2_automatizacion_delete"
CORE = "wa2_automatizacion_delete_core"
IMPORT_MODULE = "routers.whatsapp_automation_delete"


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
    legacy = fn(tree, LEGACY)
    core = fn(canon, CORE)
    if shape(legacy) != shape(core):
        raise SystemExit("automation delete body differs")

    wrapper = '''async def wa2_automatizacion_delete(auto_id: str, request: Request):\n    return await wa2_automatizacion_delete_core(\n        auto_id, request, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_delete=sb_delete, _in_filter=_in_filter,\n    )\n'''
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("automation delete already imported")
    node = fn(t2, LEGACY)
    first = min([d.lineno for d in node.decorator_list] or [node.lineno])
    cur = mid.splitlines(keepends=True)
    cur[first - 1:first - 1] = ["from routers.whatsapp_automation_delete import wa2_automatizacion_delete_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper_node = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    expected = {"_require_user", "_ids_visibles", "sb_delete", "_in_filter"}
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
        raise SystemExit("automation delete wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
