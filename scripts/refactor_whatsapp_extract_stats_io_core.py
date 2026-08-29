#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_stats_io.py"
IMPORT_MODULE = "routers.whatsapp_stats_io"
SPECS = {
    "_sb_diag": (
        "sb_diag_core",
        '''async def _sb_diag(table: str, params: dict) -> tuple[list, str]:\n    return await _sb_diag_core(table, params, get_rows=get_rows, httpx=httpx)\n''',
        {"get_rows", "httpx"},
    ),
    "_sb_get_paginado": (
        "sb_get_paginado_core",
        '''async def _sb_get_paginado(table: str, params: dict, tope: int = 40000,\n                           paralelo: int = 6) -> tuple[list, str]:\n    return await _sb_get_paginado_core(\n        table, params, tope, paralelo, _sb_diag=_sb_diag, asyncio=asyncio,\n    )\n''',
        {"_sb_diag", "asyncio"},
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
            raise SystemExit(f"stats I/O body differs: {legacy_name}")
        replacements.append((legacy.lineno, legacy.end_lineno, wrapper_text))

    lines = text.splitlines(keepends=True)
    for start, end, wrapper_text in sorted(replacements, reverse=True):
        lines[start - 1:end] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("stats I/O already imported")

    first = min(fn(t2, name).lineno for name in SPECS)
    cur = mid.splitlines(keepends=True)
    import_text = (
        "from routers.whatsapp_stats_io import (\n"
        "    sb_diag_core as _sb_diag_core,\n"
        "    sb_get_paginado_core as _sb_get_paginado_core,\n"
        ")\n\n"
    )
    cur[first - 1:first - 1] = [import_text]
    out = "".join(cur)
    t3 = ast.parse(out)

    for legacy_name, (core_name, _, expected_keywords) in SPECS.items():
        wrapper = fn(t3, legacy_name)
        target_name = f"_{core_name}"
        calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == target_name]
        if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected_keywords:
            raise SystemExit(f"stats I/O wrapper contract differs: {legacy_name}")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
