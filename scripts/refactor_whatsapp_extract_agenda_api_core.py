#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_agenda_api.py"
LEGACY = "wa2_agendar"
CORE = "wa2_agendar_core"
WRAPPER = '''async def wa2_agendar(req: AgendarReq, request: Request):\n    return await wa2_agendar_core(\n        req, request,\n        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,\n        _in_filter=_in_filter, HTTPException=HTTPException, sb_patch=sb_patch,\n        _entrenamiento_de=_entrenamiento_de, _fecha_hora_utc_iso=_fecha_hora_utc_iso,\n        sb_post=sb_post, _construir_ics=_construir_ics, _wa_send_document=_wa_send_document,\n    )\n'''
EXPECTED = {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "sb_patch",
            "_entrenamiento_de", "_fecha_hora_utc_iso", "sb_post", "_construir_ics", "_wa_send_document"}


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
    legacy = fn(tree, LEGACY)
    core = fn(canon, CORE)
    if shape(legacy) != shape(core):
        raise SystemExit("agenda API body differs")

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_agenda_api" for n in t2.body):
        raise SystemExit("agenda API already imported")

    wrapper = fn(t2, LEGACY)
    insert_line = min([d.lineno for d in wrapper.decorator_list] or [wrapper.lineno])
    cur = mid.splitlines(keepends=True)
    cur[insert_line - 1:insert_line - 1] = ["from routers.whatsapp_agenda_api import wa2_agendar_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper2 = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper2) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != EXPECTED:
        raise SystemExit("agenda API wrapper contract differs")
    if not wrapper2.decorator_list:
        raise SystemExit("agenda API route decorator lost")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
