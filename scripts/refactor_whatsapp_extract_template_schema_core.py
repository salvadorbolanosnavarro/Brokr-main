from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_template_schema.py")
TARGETS = ("PlantillaCrearReq", "PlantillaEnviarReq")
IMPORT = (
    "from routers.whatsapp_template_schema import (\n"
    "    PlantillaCrearReq, PlantillaEnviarReq,\n"
    ")\n"
)


def find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SystemExit(f"missing class {name}")


src = SRC.read_text()
schema_src = SCHEMA.read_text()
src_tree = ast.parse(src)
schema_tree = ast.parse(schema_src)
old_nodes = [find_class(src_tree, name) for name in TARGETS]
canonical_nodes = [find_class(schema_tree, name) for name in TARGETS]

for old, canonical, name in zip(old_nodes, canonical_nodes, TARGETS):
    if ast.dump(old, include_attributes=False) != ast.dump(canonical, include_attributes=False):
        raise SystemExit(f"template schema class differs for {name}")

if IMPORT.strip() in src:
    raise SystemExit("template schema extraction already applied")

lines = src.splitlines(keepends=True)
for node in sorted(old_nodes, key=lambda n: n.lineno, reverse=True):
    start = node.lineno - 1
    end = node.end_lineno
    lines[start:end] = []

insert_at = min(node.lineno for node in old_nodes) - 1
lines[insert_at:insert_at] = [IMPORT, "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
