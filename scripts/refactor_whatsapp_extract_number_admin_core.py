from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_number_admin.py")
PAIRS = [
    ("wa2_numero_verificar", "wa2_numero_verificar_core"),
    ("wa2_numeros_list", "wa2_numeros_list_core"),
    ("wa2_numero_patch", "wa2_numero_patch_core"),
]


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
for old_name, core_name in PAIRS:
    if dump_body(find_fn(src_tree, old_name)) != dump_body(find_fn(core_tree, core_name)):
        raise SystemExit(f"body mismatch: {old_name}")

if "from routers.whatsapp_number_admin import" in src:
    raise SystemExit("number admin extraction already applied")

replacements = {
    "wa2_numero_verificar": '''@router.get("/numeros/{numero_id}/verificar")
async def wa2_numero_verificar(numero_id: str, request: Request):
    return await wa2_numero_verificar_core(
        numero_id, request,
        _require_user=_require_user, sb_get=sb_get, HTTPException=HTTPException,
        httpx=httpx, GRAPH_API=GRAPH_API, WA2_WEBHOOK_URL=WA2_WEBHOOK_URL,
        sb_patch=sb_patch,
    )
''',
    "wa2_numeros_list": '''@router.get("/numeros")
async def wa2_numeros_list(request: Request):
    return await wa2_numeros_list_core(
        request, _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter,
    )
''',
    "wa2_numero_patch": '''@router.patch("/numeros/{numero_id}")
async def wa2_numero_patch(numero_id: str, req: NumeroPatchReq, request: Request):
    return await wa2_numero_patch_core(
        numero_id, req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles, _now=_now,
        _normaliza_mx=_normaliza_mx, sb_patch=sb_patch, _in_filter=_in_filter,
    )
''',
}

lines = src.splitlines(keepends=True)
items = []
for name, _ in PAIRS:
    node = find_fn(src_tree, name)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    items.append((start, node.end_lineno, replacements[name]))

for start, end, repl in sorted(items, reverse=True):
    lines[start:end] = [repl + "\n"]

new = "".join(lines)
first = min(x[0] for x in items)
# Insert import immediately before first extracted route.
new_lines = new.splitlines(keepends=True)
# Re-parse after replacements to find verify wrapper's decorator location.
tmp_tree = ast.parse(new)
verify = find_fn(tmp_tree, "wa2_numero_verificar")
insert_at = min([verify.lineno] + [d.lineno for d in verify.decorator_list]) - 1
import_block = '''from routers.whatsapp_number_admin import (
    wa2_numero_verificar_core, wa2_numeros_list_core, wa2_numero_patch_core,
)

'''
new_lines[insert_at:insert_at] = [import_block]
new = "".join(new_lines)
ast.parse(new)
SRC.write_text(new)
