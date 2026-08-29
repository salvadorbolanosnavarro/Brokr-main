#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_campaign_variables.py"
TARGET = "_variables_para"
CORE_NAME = "variables_para"
IMPORT_MODULE = "routers.whatsapp_campaign_variables"


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
    legacy = fn(tree, TARGET)
    core = fn(canon, CORE_NAME)
    if shape(legacy) != shape(core):
        raise SystemExit("campaign variables body differs")

    lines = text.splitlines(keepends=True)
    wrapper = (
        "def _variables_para(contacto: dict, variables: list) -> list:\n"
        "    return _variables_para_core(contacto, variables)\n"
    )
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("campaign variables already imported")

    wrapped = fn(t2, TARGET)
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_campaign_variables import variables_para as _variables_para_core\n\n"
    )
    cur[wrapped.lineno - 1:wrapped.lineno - 1] = [import_text]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper_node = fn(t3, TARGET)
    calls = [n for n in ast.walk(wrapper_node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_variables_para_core"]
    if len(calls) != 1:
        raise SystemExit("campaign variables wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
