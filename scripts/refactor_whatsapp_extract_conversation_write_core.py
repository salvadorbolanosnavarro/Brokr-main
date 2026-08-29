#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_conversation_write.py"
LEGACY = "wa2_conversacion_patch"
CORE = "wa2_conversacion_patch_core"
WRAPPER = '''async def wa2_conversacion_patch(conversacion_id: str, req: ConvPatchReq, request: Request):\n    return await wa2_conversacion_patch_core(\n        conversacion_id, req, request,\n        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,\n        _in_filter=_in_filter, HTTPException=HTTPException, sb_patch=sb_patch,\n    )\n'''
EXPECTED = {"_require_user", "_ids_visibles", "sb_get", "_in_filter", "HTTPException", "sb_patch"}


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
        raise SystemExit("conversation write body differs")

    lines = text.splitlines(keepends=True)
    lines[legacy.lineno - 1:legacy.end_lineno] = [WRAPPER, "\n"]
    mid = "".join(lines)
    t2 = ast.parse(mid)
    if any(isinstance(n, ast.ImportFrom) and n.module == "routers.whatsapp_conversation_write" for n in t2.body):
        raise SystemExit("conversation write already imported")

    wrapper = fn(t2, LEGACY)
    insert_line = min([d.lineno for d in wrapper.decorator_list] or [wrapper.lineno])
    cur = mid.splitlines(keepends=True)
    cur[insert_line - 1:insert_line - 1] = ["from routers.whatsapp_conversation_write import wa2_conversacion_patch_core\n\n"]
    out = "".join(cur)
    t3 = ast.parse(out)
    wrapper2 = fn(t3, LEGACY)
    calls = [n for n in ast.walk(wrapper2) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == CORE]
    if len(calls) != 1 or {k.arg for k in calls[0].keywords} != EXPECTED:
        raise SystemExit("conversation write wrapper contract differs")
    if not wrapper2.decorator_list:
        raise SystemExit("conversation write route decorator lost")

    SOURCE.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
