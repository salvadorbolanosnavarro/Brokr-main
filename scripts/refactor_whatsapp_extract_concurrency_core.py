#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_concurrency.py"
TARGET = "_lock_conv"
CORE_NAME = "lock_conv"
IMPORT_MODULE = "routers.whatsapp_concurrency"


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
        raise SystemExit("conversation lock body differs")

    wrapper_text = '''def _lock_conv(conversacion_id: str) -> asyncio.Lock:
    return _lock_conv_core(conversacion_id, _LOCKS=_LOCKS, asyncio=asyncio)
'''
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("conversation concurrency already imported")

    wrapped = fn(t2, TARGET)
    cur = mid.splitlines(keepends=True)
    cur[wrapped.lineno - 1:wrapped.lineno - 1] = [
        "from routers.whatsapp_concurrency import lock_conv as _lock_conv_core\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper = fn(t3, TARGET)
    calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_lock_conv_core"]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != {"_LOCKS", "asyncio"}:
        raise SystemExit("conversation lock wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
