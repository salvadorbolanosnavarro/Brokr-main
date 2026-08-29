from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
MODULE = "routers.whatsapp_message_state"
WRAPPER = "_resolver_inmueble_id"
CORE = "_resolver_inmueble_id_core"

EXPECTED_WRAPPER = ast.parse(
    "def _resolver_inmueble_id(inmueble_txt: str, ultimas: list) -> str | None:\n"
    "    return _resolver_inmueble_id_core(inmueble_txt, ultimas)\n"
).body[0]


def find_wrapper(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == WRAPPER:
            return node
    raise SystemExit(f"missing wrapper {WRAPPER}")


def find_import(tree: ast.Module) -> ast.ImportFrom:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            names = {alias.name for alias in node.names}
            if CORE in names:
                return node
    raise SystemExit(f"missing import of {CORE} from {MODULE}")


src = SRC.read_text()
tree = ast.parse(src)
wrapper = find_wrapper(tree)
import_node = find_import(tree)

if ast.dump(wrapper, include_attributes=False) != ast.dump(EXPECTED_WRAPPER, include_attributes=False):
    raise SystemExit("resolver wrapper differs from expected pure forwarder")

aliases = []
for alias in import_node.names:
    if alias.name == CORE:
        aliases.append(ast.alias(name=CORE, asname=WRAPPER))
    else:
        aliases.append(alias)
new_import = ast.ImportFrom(module=MODULE, names=aliases, level=0)
new_import_text = ast.unparse(new_import) + "\n"

lines = src.splitlines(keepends=True)
del lines[wrapper.lineno - 1:wrapper.end_lineno]
lines[import_node.lineno - 1:import_node.end_lineno] = [new_import_text]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
