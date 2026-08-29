from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
STATE = Path("routers/whatsapp_runtime_state.py")
TARGETS = ("_LOCKS", "_AUTO_ULTIMA")
IMPORT = "from routers.whatsapp_runtime_state import _LOCKS, _AUTO_ULTIMA\n"


def assignment_name(node: ast.stmt) -> str | None:
    if not isinstance(node, ast.AnnAssign):
        return None
    return node.target.id if isinstance(node.target, ast.Name) else None


def find_assign(tree: ast.Module, name: str) -> ast.AnnAssign:
    for node in tree.body:
        if assignment_name(node) == name:
            return node
    raise SystemExit(f"missing annotated assignment {name}")


src = SRC.read_text()
state_src = STATE.read_text()
src_tree = ast.parse(src)
state_tree = ast.parse(state_src)
old_nodes = [find_assign(src_tree, name) for name in TARGETS]
canonical_nodes = [find_assign(state_tree, name) for name in TARGETS]
for name, old, canonical in zip(TARGETS, old_nodes, canonical_nodes):
    if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
        raise SystemExit(f"runtime state {name} differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("runtime state extraction already applied")

lines = src.splitlines(keepends=True)
first = min(old_nodes, key=lambda node: node.lineno)
for node in sorted(old_nodes, key=lambda node: node.lineno, reverse=True):
    del lines[node.lineno - 1:node.end_lineno]
lines[first.lineno - 1:first.lineno - 1] = [IMPORT, "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
