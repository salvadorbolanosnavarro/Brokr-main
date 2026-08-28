#!/usr/bin/env python3
"""Extract pure WhatsApp statistics helpers from the legacy monolith.

The transform is deliberately bounded: it only removes three top-level helper
functions after proving their executable AST (including signatures and every
statement except docstrings) is identical to routers/whatsapp_stats.py. Legacy
docstrings are asserted and restored after import so introspection is preserved.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_stats.py"
TARGETS = ("_dt", "_mediana", "_agrega_ventana")
LEGACY_DOCS = {
    "_dt": "Parsea un timestamptz de Postgres a datetime con zona. Nunca revienta.",
    "_mediana": None,
    "_agrega_ventana": "Todos los números de WhatsApp para una ventana de tiempo.",
}
IMPORT_TEXT = "from routers.whatsapp_stats import _agrega_ventana, _dt, _mediana\n"
DOC_RESTORE_TEXT = (
    '_dt.__doc__ = "Parsea un timestamptz de Postgres a datetime con zona. Nunca revienta."\n'
    '_agrega_ventana.__doc__ = "Todos los números de WhatsApp para una ventana de tiempo."\n'
)


def top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
    cloned = copy.deepcopy(node)
    if (
        cloned.body
        and isinstance(cloned.body[0], ast.Expr)
        and isinstance(cloned.body[0].value, ast.Constant)
        and isinstance(cloned.body[0].value.value, str)
    ):
        cloned.body = cloned.body[1:]
    return cloned


def executable_dump(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return ast.dump(without_docstring(node), annotate_fields=True, include_attributes=False)


def insertion_line(tree: ast.Module) -> int:
    """Return a deterministic source line for a new import without text anchors."""
    last_import_end = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_end = max(last_import_end, node.end_lineno or node.lineno)
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node is tree.body[0]
        ):
            continue
        if last_import_end:
            break
    if not last_import_end:
        raise SystemExit("refusing stats extraction: no top-level import block found")
    return last_import_end


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))

    source_fns = top_level_functions(source_tree)
    canonical_fns = top_level_functions(canonical_tree)

    missing_source = [name for name in TARGETS if name not in source_fns]
    missing_canonical = [name for name in TARGETS if name not in canonical_fns]
    if missing_source:
        raise SystemExit(f"refusing stats extraction: missing legacy functions {missing_source}")
    if missing_canonical:
        raise SystemExit(f"refusing stats extraction: missing canonical functions {missing_canonical}")

    wrong_docs = [name for name in TARGETS if ast.get_docstring(source_fns[name], clean=False) != LEGACY_DOCS[name]]
    if wrong_docs:
        raise SystemExit(f"refusing stats extraction: unexpected legacy docstrings for {wrong_docs}")

    mismatched = [
        name
        for name in TARGETS
        if executable_dump(source_fns[name]) != executable_dump(canonical_fns[name])
    ]
    if mismatched:
        raise SystemExit(f"refusing stats extraction: executable AST mismatch for {mismatched}")

    if IMPORT_TEXT.strip() in source:
        raise SystemExit("refusing stats extraction: canonical stats import already present")

    lines = source.splitlines(keepends=True)
    removals = sorted(
        (source_fns[name].lineno, source_fns[name].end_lineno, name)
        for name in TARGETS
    )

    remove_lines: set[int] = set()
    for start, end, _name in removals:
        if end is None:
            raise SystemExit("refusing stats extraction: AST node lacks end_lineno")
        remove_lines.update(range(start, end + 1))
        if end < len(lines) and not lines[end].strip():
            remove_lines.add(end + 1)

    insert_after = insertion_line(source_tree)
    output: list[str] = []
    inserted = False
    for lineno, line in enumerate(lines, start=1):
        if lineno not in remove_lines:
            output.append(line)
        if lineno == insert_after:
            output.append(IMPORT_TEXT)
            output.append(DOC_RESTORE_TEXT)
            inserted = True

    if not inserted:
        raise SystemExit("refusing stats extraction: failed to place canonical import")

    updated = "".join(output)
    updated_tree = ast.parse(updated, filename=str(SOURCE))
    updated_fns = top_level_functions(updated_tree)
    leftovers = [name for name in TARGETS if name in updated_fns]
    if leftovers:
        raise SystemExit(f"refusing stats extraction: legacy functions remain {leftovers}")

    imports = [
        node
        for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_stats"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing stats extraction: expected exactly one canonical stats import")
    imported_names = {alias.asname or alias.name for alias in imports[0].names}
    if imported_names != set(TARGETS):
        raise SystemExit(f"refusing stats extraction: unexpected imported names {sorted(imported_names)}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp stats helpers: " + ", ".join(TARGETS))


if __name__ == "__main__":
    main()
