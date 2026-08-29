#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_campaign_access.py"
LEGACY = "_numero_visible"
CORE = "_numero_visible_core"
WRAPPER = '''async def _numero_visible(request: Request, numero_id: str) -> tuple[str, dict]:\n    return await _numero_visible_core(\n        request, numero_id, _require_user=_require_user, _ids_visibles=_ids_visibles,\n        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,\n    )\n'''
EXPECTED = {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException"}


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
        raise SystemExit("campaign access bodies differ")
    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_campaign_access" for n in t2.body):
        raise SystemExit("campaign access already imported")
    wrapper = fn(t2, LEGACY)
    cur = mid.splitlines(keepends=True)
    cur[wrapper.lineno - 1:wrapper.lineno - 1] = ["from routers.whatsapp_campaign_access import _numero_visible_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper2 = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper2) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != EXPECTED:
        raise SystemExit("campaign access wrapper contract differs")
    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
