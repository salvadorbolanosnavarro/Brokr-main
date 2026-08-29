from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
SCHEMA = Path("routers/whatsapp_campaign_schema.py")
TARGETS = ("CampanaAudienciaReq", "CampanaCrearReq")
IMPORT = (
    "from routers.whatsapp_campaign_schema import (\n"
    "    CampanaAudienciaReq, CampanaCrearReq,\n"
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
        raise SystemExit(f"campaign schema class differs for {name}")

if IMPORT.strip() in src:
    raise SystemExit("campaign schema extraction already applied")

lines = src.splitlines(keepends=True)
start = min(node.lineno for node in old_nodes) - 1
end = max(node.end_lineno for node in old_nodes)
new = "".join(lines[:start]) + IMPORT + "\n" + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
