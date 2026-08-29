from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_number_delete.py")
TARGET = "wa2_numero_delete"
CORE_NAME = "wa2_numero_delete_core"


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
    raise SystemExit("number delete core body differs from whatsapp.py")
if "from routers.whatsapp_number_delete import wa2_numero_delete_core" in src:
    raise SystemExit("number delete extraction already applied")

lines = src.splitlines(keepends=True)
start = min((d.lineno for d in old.decorator_list), default=old.lineno) - 1
end = old.end_lineno
replacement = '''from routers.whatsapp_number_delete import wa2_numero_delete_core

@router.delete("/numeros/{numero_id}")
async def wa2_numero_delete(numero_id: str, request: Request):
    return await wa2_numero_delete_core(
        numero_id, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, sb_get=sb_get,
        _in_filter=_in_filter, HTTPException=HTTPException, httpx=httpx,
        GRAPH_API=GRAPH_API, _borrar_archivos=_borrar_archivos,
        sb_delete=sb_delete, log=log,
    )

'''
new = "".join(lines[:start]) + replacement + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
