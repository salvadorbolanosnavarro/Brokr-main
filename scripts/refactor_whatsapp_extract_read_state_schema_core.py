from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_read_state_schema.py")
TARGET = "LecturaReq"
IMPORT = "from routers.whatsapp_read_state_schema import LecturaReq\n"


def find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SystemExit(f"missing class {name}")


src = SRC.read_text()
schema_src = SCHEMA.read_text()
src_tree = ast.parse(src)
schema_tree = ast.parse(schema_src)
old = find_class(src_tree, TARGET)
canonical = find_class(schema_tree, TARGET)
if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
    raise SystemExit("read-state schema class differs from whatsapp.py")
if IMPORT.strip() in src:
    raise SystemExit("read-state schema extraction already applied")

lines = src.splitlines(keepends=True)
start = old.lineno - 1
end = old.end_lineno
new = "".join(lines[:start]) + IMPORT + "\n" + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
