from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
MODULE = "routers.whatsapp_campaign_variables"
WRAPPER = "_variables_para"
CORE = "variables_para"

EXPECTED_WRAPPER = ast.parse(
    "def _variables_para(contacto: dict, variables: list) -> list:\n"
    "    return _variables_para_core(contacto, variables)\n"
).body[0]


def find_wrapper(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == WRAPPER:
            return node
    raise SystemExit(f"missing wrapper {WRAPPER}")


def find_import(tree: ast.Module) -> ast.ImportFrom:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            if any(alias.name == CORE and alias.asname == "_variables_para_core" for alias in node.names):
                return node
    raise SystemExit(f"missing import of {CORE} as _variables_para_core from {MODULE}")


src = SRC.read_text()
tree = ast.parse(src)
wrapper = find_wrapper(tree)
import_node = find_import(tree)
if ast.dump(wrapper, include_attributes=False) != ast.dump(EXPECTED_WRAPPER, include_attributes=False):
    raise SystemExit("campaign variables wrapper differs from expected pure forwarder")

aliases = [
    ast.alias(name=alias.name, asname=WRAPPER if alias.name == CORE and alias.asname == "_variables_para_core" else alias.asname)
    for alias in import_node.names
]
new_import_text = ast.unparse(ast.ImportFrom(module=MODULE, names=aliases, level=0)) + "\n"

lines = src.splitlines(keepends=True)
del lines[wrapper.lineno - 1:wrapper.end_lineno]
lines[import_node.lineno - 1:import_node.end_lineno] = [new_import_text]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
