#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_flow_state.py"
LEGACY = "_flujo_estado_borrar"
CORE = "_flujo_estado_borrar_core"


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
        raise SystemExit("flow state delete body differs")

    wrapper = '''async def _flujo_estado_borrar(conversacion_id: str) -> None:\n    return await _flujo_estado_borrar_core(conversacion_id, sb_delete=sb_delete)\n'''
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    out = "".join(lines)
    t2 = ast.parse(out)

    imports = [n for n in t2.body if isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_flow_state"]
    if len(imports) != 1:
        raise SystemExit(f"expected one whatsapp_flow_state import, found {len(imports)}")
    imp = imports[0]
    if any(a.name == CORE for a in imp.names):
        raise SystemExit("flow state delete already imported")

    cur = out.splitlines(keepends=True)
    line = cur[imp.lineno - 1]
    if line.rstrip().endswith(")") or "(" in line:
        raise SystemExit("unexpected multiline flow state import")
    line = line.rstrip("\n") + f", {CORE}\n"
    cur[imp.lineno - 1] = line
    final = "".join(cur)
    t3 = ast.parse(final)
    wrapper_node = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != {"sb_delete"}:
        raise SystemExit("flow state delete wrapper contract differs")
    SOURCE.write_text(final, encoding="utf-8")


if __name__ == "__main__":
    main()
