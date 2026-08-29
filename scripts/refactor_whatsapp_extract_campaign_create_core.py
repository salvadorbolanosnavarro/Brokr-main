#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_campaign_create.py"
TARGET = "wa2_campana_crear"
CORE_NAME = "wa2_campana_crear_core"
IMPORT_MODULE = "routers.whatsapp_campaign_create"


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
        raise SystemExit("campaign create body differs")

    wrapper_text = '''async def wa2_campana_crear(req: CampanaCrearReq, request: Request, background: BackgroundTasks):
    return await wa2_campana_crear_core(
        req, request, background,
        _numero_visible=_numero_visible, _audiencia_campana=_audiencia_campana,
        WA2_CAMPANA_TOPE=WA2_CAMPANA_TOPE, HTTPException=HTTPException,
        _now=_now, sb_post=sb_post, _correr_campana=_correr_campana,
    )
'''
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [wrapper_text, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == IMPORT_MODULE for n in t2.body):
        raise SystemExit("campaign create already imported")

    wrapped = fn(t2, TARGET)
    insert_line = min([d.lineno for d in wrapped.decorator_list] or [wrapped.lineno])
    cur = mid.splitlines(keepends=True)
    cur[insert_line - 1:insert_line - 1] = [
        "from routers.whatsapp_campaign_create import wa2_campana_crear_core\n\n"
    ]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper = fn(t3, TARGET)
    calls = [n for n in ast.walk(wrapper) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE_NAME]
    expected = {
        "_numero_visible", "_audiencia_campana", "WA2_CAMPANA_TOPE",
        "HTTPException", "_now", "sb_post", "_correr_campana",
    }
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != expected:
        raise SystemExit("campaign create wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
