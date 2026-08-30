from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path("routers/firmas.py")
CORE_MODULE = "core.firmas_utils"
FUNCTIONS = (
    "_limpio",
    "_folio",
    "_sha256",
    "_fecha_larga",
    "_tel",
    "_email_ok",
    "_mask_tel",
    "_mask_email",
)
CONSTANT = "_ALFABETO_FOLIO"
IMPORT_LINE = (
    "from core.firmas_utils import "
    "_email_ok, _fecha_larga, _folio, _limpio, _mask_email, _mask_tel, _sha256, _tel\n"
)


def _assigned_names(node: ast.Assign) -> set[str]:
    names: set[str] = set()
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)

    if any(
        isinstance(node, ast.ImportFrom) and node.module == CORE_MODULE
        for node in tree.body
    ):
        raise SystemExit("firmas utils import already present")

    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    constant_node: ast.Assign | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS:
            if node.name in functions:
                raise SystemExit(f"duplicate target function: {node.name}")
            functions[node.name] = node
        elif isinstance(node, ast.Assign) and CONSTANT in _assigned_names(node):
            if constant_node is not None:
                raise SystemExit(f"duplicate target constant: {CONSTANT}")
            constant_node = node

    missing = sorted(set(FUNCTIONS) - set(functions))
    if missing:
        raise SystemExit(f"missing firmas utility functions: {missing}")
    if constant_node is None:
        raise SystemExit(f"missing firmas utility constant: {CONSTANT}")

    async_targets = sorted(
        name for name, node in functions.items() if isinstance(node, ast.AsyncFunctionDef)
    )
    if async_targets:
        raise SystemExit(f"utility targets unexpectedly async: {async_targets}")

    # Keep this extraction deliberately bounded to the known pure helper block.
    ordered_lines = [functions[name].lineno for name in FUNCTIONS]
    if ordered_lines != sorted(ordered_lines):
        raise SystemExit("firmas utility function order changed unexpectedly")
    if not (functions["_limpio"].lineno < constant_node.lineno < functions["_folio"].lineno):
        raise SystemExit("firmas utility block shape changed unexpectedly")

    core_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core.")
    ]
    if not core_imports:
        raise SystemExit("no Core imports found in firmas router")
    insert_after = max(node.end_lineno or node.lineno for node in core_imports)

    spans = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in [constant_node, *functions.values()]
    ]
    lines = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start - 1 : end]

    # Account for deleted lines that originally appeared before the import point.
    removed_before = sum(
        end - start + 1
        for start, end in spans
        if end <= insert_after
    )
    adjusted_insert_after = insert_after - removed_before
    lines.insert(adjusted_insert_after, IMPORT_LINE)

    updated = "".join(lines)
    updated_tree = ast.parse(updated)

    remaining_defs = {
        node.name
        for node in updated_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTIONS
    }
    if remaining_defs:
        raise SystemExit(f"target utility definitions remained: {sorted(remaining_defs)}")
    if any(
        isinstance(node, ast.Assign) and CONSTANT in _assigned_names(node)
        for node in updated_tree.body
    ):
        raise SystemExit(f"target utility constant remained: {CONSTANT}")

    imports = [
        node
        for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == CORE_MODULE
    ]
    if len(imports) != 1:
        raise SystemExit(f"expected one firmas utils import, found {len(imports)}")
    imported = {alias.asname or alias.name for alias in imports[0].names}
    if imported != set(FUNCTIONS):
        raise SystemExit(f"unexpected firmas utils import bindings: {sorted(imported)}")

    TARGET.write_text(updated, encoding="utf-8")
    print("extracted pure firmas utilities to core.firmas_utils")


if __name__ == "__main__":
    main()
