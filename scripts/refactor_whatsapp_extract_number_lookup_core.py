from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_number_lookup.py")
TARGET = "_get_numero"
CORE_NAME = "_get_numero_core"


def find_fn(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise SystemExit(f"missing {name}")


def dump_body(node):
    return [ast.dump(x, include_attributes=False) for x in node.body]


src = SRC.read_text()
core_src = CORE.read_text()
src_tree = ast.parse(src)
core_tree = ast.parse(core_src)
old = find_fn(src_tree, TARGET)
core = find_fn(core_tree, CORE_NAME)
if dump_body(old) != dump_body(core):
    raise SystemExit("number lookup core body differs from whatsapp.py")
if "from routers.whatsapp_number_lookup import _get_numero_core" in src:
    raise SystemExit("number lookup extraction already applied")

lines = src.splitlines(keepends=True)
start = old.lineno - 1
end = old.end_lineno
replacement = '''from routers.whatsapp_number_lookup import _get_numero_core

async def _get_numero(phone_number_id: str) -> dict | None:
    return await _get_numero_core(phone_number_id, sb_get=sb_get)

'''
new = "".join(lines[:start]) + replacement + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
