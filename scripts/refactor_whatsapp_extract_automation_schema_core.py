from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_automation_schema.py")
ASSIGNS = ("_AUTO_TIPOS", "_FLUJO_CAMPOS")
CLASSES = ("AutomatizacionReq",)
IMPORT = (
    "from routers.whatsapp_automation_schema import (\n"
    "    AutomatizacionReq, _AUTO_TIPOS, _FLUJO_CAMPOS,\n"
    ")\n"
)


def find_named(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return node
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SystemExit(f"missing top-level node {name}")


def semantic_dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


src = SRC.read_text()
schema_src = SCHEMA.read_text()
src_tree = ast.parse(src)
schema_tree = ast.parse(schema_src)

for name in (*ASSIGNS, *CLASSES):
    current = find_named(src_tree, name)
    canonical = find_named(schema_tree, name)
    if semantic_dump(current) != semantic_dump(canonical):
        raise SystemExit(f"automation schema node differs: {name}")

if IMPORT.strip() in src:
    raise SystemExit("automation schema extraction already applied")

nodes = [find_named(src_tree, name) for name in (*ASSIGNS, *CLASSES)]
lines = src.splitlines(keepends=True)
for node in sorted(nodes, key=lambda item: item.lineno, reverse=True):
    del lines[node.lineno - 1:node.end_lineno]

insert_at = min(node.lineno for node in nodes) - 1
lines.insert(insert_at, IMPORT + "\n")
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
