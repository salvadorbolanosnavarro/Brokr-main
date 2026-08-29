from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CONFIG = Path("routers/whatsapp_static_config.py")
TARGETS = ("GRAPH_API", "HISTORY_LIMIT", "WA_MAX_TEXTO")
IMPORT = "from routers.whatsapp_static_config import GRAPH_API, HISTORY_LIMIT, WA_MAX_TEXTO\n"


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
config_src = CONFIG.read_text()
src_tree = ast.parse(src)
config_tree = ast.parse(config_src)
old_nodes = [find_assign(src_tree, name) for name in TARGETS]
canonical_nodes = [find_assign(config_tree, name) for name in TARGETS]
for name, old, canonical in zip(TARGETS, old_nodes, canonical_nodes):
    if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
        raise SystemExit(f"static config {name} differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("static config extraction already applied")

lines = src.splitlines(keepends=True)
first = min(old_nodes, key=lambda node: node.lineno)
for node in sorted(old_nodes, key=lambda node: node.lineno, reverse=True):
    del lines[node.lineno - 1:node.end_lineno]
lines[first.lineno - 1:first.lineno - 1] = [IMPORT, "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
