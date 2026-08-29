#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_stats_api.py"
TARGET = "wa2_estadisticas"
CORE_NAME = "wa2_estadisticas_core"
IMPORT_MODULE = "routers.whatsapp_stats_api"


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
        raise SystemExit("statistics API body differs")

    wrapper_text = '''async def wa2_estadisticas(request: Request, zona: str | None = None):
    return await wa2_estadisticas_core(
        request, zona,
        _require_user=_require_user, _ids_visibles=_ids_visibles, _in_filter=_in_filter,
        _ZONA_DEFAULT=_ZONA_DEFAULT, asyncio=asyncio, _sb_diag=_sb_diag,
        _sb_get_paginado=_sb_get_paginado, log=log, datetime=datetime,
        timezone=timezone, _agrega_ventana=_agrega_ventana,
        _VENTANAS_ESTAD=_VENTANAS_ESTAD, _now=_now,
    )
'''
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper_text]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("statistics API already imported")

    wrapped = fn(t2, TARGET)
    insert_line = min([d.lineno for d in wrapped.decorator_list] or [wrapped.lineno])
    cur = mid.splitlines(keepends=True)
    cur[insert_line - 1:insert_line - 1] = [
        "from routers.whatsapp_stats_api import wa2_estadisticas_core\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper = fn(t3, TARGET)
    calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE_NAME]
    expected = {
        "_require_user", "_ids_visibles", "_in_filter", "_ZONA_DEFAULT", "asyncio",
        "_sb_diag", "_sb_get_paginado", "log", "datetime", "timezone",
        "_agrega_ventana", "_VENTANAS_ESTAD", "_now",
    }
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
        raise SystemExit("statistics API wrapper contract differs")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
