from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
POLICY = Path("routers/whatsapp_optout_policy.py")
TARGET = "_OPT_OUT_PALABRAS"
IMPORT = "from routers.whatsapp_optout_policy import _OPT_OUT_PALABRAS\n"


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
policy_src = POLICY.read_text()
src_tree = ast.parse(src)
policy_tree = ast.parse(policy_src)
old = find_assign(src_tree, TARGET)
canonical = find_assign(policy_tree, TARGET)
if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
    raise SystemExit("opt-out policy differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("opt-out policy extraction already applied")

lines = src.splitlines(keepends=True)
del lines[old.lineno - 1:old.end_lineno]
lines[old.lineno - 1:old.lineno - 1] = [IMPORT, "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
