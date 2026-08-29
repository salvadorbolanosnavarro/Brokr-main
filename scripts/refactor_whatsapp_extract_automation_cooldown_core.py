from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_automation_schema.py")
TARGET = "_AUTO_COOLDOWN_SEG"
OLD_IMPORT = (
    "from routers.whatsapp_automation_schema import (\n"
    "    AutomatizacionReq, _AUTO_TIPOS, _FLUJO_CAMPOS,\n"
    ")"
)
NEW_IMPORT = (
    "from routers.whatsapp_automation_schema import (\n"
    "    AutomatizacionReq, _AUTO_TIPOS, _FLUJO_CAMPOS, _AUTO_COOLDOWN_SEG,\n"
    ")"
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
schema_src = SCHEMA.read_text()
src_tree = ast.parse(src)
schema_tree = ast.parse(schema_src)
old = find_assign(src_tree, TARGET)
canonical = find_assign(schema_tree, TARGET)
if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
    raise SystemExit("automation cooldown differs from whatsapp.py")
if OLD_IMPORT not in src:
    raise SystemExit("expected automation schema import not found")
if NEW_IMPORT in src:
    raise SystemExit("automation cooldown extraction already applied")

lines = src.splitlines(keepends=True)
del lines[old.lineno - 1:old.end_lineno]
new = "".join(lines).replace(OLD_IMPORT, NEW_IMPORT, 1)
ast.parse(new)
SRC.write_text(new)
