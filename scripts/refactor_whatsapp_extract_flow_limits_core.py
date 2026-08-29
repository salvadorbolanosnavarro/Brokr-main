from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
LIMITS = Path("routers/whatsapp_flow_limits.py")
TARGETS = (
    "_FLUJO_MAX_PASOS_POR_TURNO",
    "_FLUJO_CADUCA_HORAS",
    "_FLUJO_MAX_REINTENTOS",
)
IMPORT = (
    "from routers.whatsapp_flow_limits import (\n"
    "    _FLUJO_MAX_PASOS_POR_TURNO, _FLUJO_CADUCA_HORAS, _FLUJO_MAX_REINTENTOS,\n"
    ")\n"
)


def assignment_name(node: ast.stmt) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def find_assign(tree: ast.Module, name: str) -> ast.Assign:
    for node in tree.body:
        if assignment_name(node) == name:
            return node
    raise SystemExit(f"missing assignment {name}")


src = SRC.read_text()
limits_src = LIMITS.read_text()
src_tree = ast.parse(src)
limits_tree = ast.parse(limits_src)
old_nodes = [find_assign(src_tree, name) for name in TARGETS]
canonical_nodes = [find_assign(limits_tree, name) for name in TARGETS]
for name, old, canonical in zip(TARGETS, old_nodes, canonical_nodes):
    if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
        raise SystemExit(f"flow limit {name} differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("flow limits extraction already applied")

lines = src.splitlines(keepends=True)
for node in sorted(old_nodes, key=lambda n: n.lineno, reverse=True):
    del lines[node.lineno - 1:node.end_lineno]

insert_at = min(node.lineno for node in old_nodes) - 1
lines[insert_at:insert_at] = [IMPORT, "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
