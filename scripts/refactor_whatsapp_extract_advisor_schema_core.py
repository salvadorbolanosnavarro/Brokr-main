from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_advisor_schema.py")
TARGET = "ASESOR_TOOLS"
IMPORT = "from routers.whatsapp_advisor_schema import ASESOR_TOOLS\n"


def find_assign(tree: ast.Module, name: str) -> ast.Assign:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node
    raise SystemExit(f"missing assignment {name}")


src = SRC.read_text()
schema_src = SCHEMA.read_text()
src_tree = ast.parse(src)
schema_tree = ast.parse(schema_src)
old = find_assign(src_tree, TARGET)
canonical = find_assign(schema_tree, TARGET)
if ast.dump(old.value, include_attributes=False) != ast.dump(canonical.value, include_attributes=False):
    raise SystemExit("advisor tool schema differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("advisor schema extraction already applied")

lines = src.splitlines(keepends=True)
start = old.lineno - 1
end = old.end_lineno
new = "".join(lines[:start]) + IMPORT + "\n" + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
