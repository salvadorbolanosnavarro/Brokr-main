from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path("routers/firmas.py")
CORE_MODULE = "core.firmas_utils"
TARGET_FUNCTIONS = ("_mail_layout", "_le_toca", "_resumen_estado")
EXPECTED_EXISTING_IMPORTS = {
    "_email_ok",
    "_fecha_larga",
    "_folio",
    "_limpio",
    "_mask_email",
    "_mask_tel",
    "_tel",
}
EXPECTED_FINAL_IMPORTS = EXPECTED_EXISTING_IMPORTS | set(TARGET_FUNCTIONS)
PROTECTED_LOCAL_FUNCTIONS = {"_sha256"}


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)

    target_defs: dict[str, ast.FunctionDef] = {}
    protected_defs: set[str] = set()
    core_import: ast.ImportFrom | None = None

    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in TARGET_FUNCTIONS:
            raise SystemExit(f"target helper unexpectedly async: {node.name}")
        if isinstance(node, ast.FunctionDef):
            if node.name in TARGET_FUNCTIONS:
                if node.name in target_defs:
                    raise SystemExit(f"duplicate target helper: {node.name}")
                target_defs[node.name] = node
            if node.name in PROTECTED_LOCAL_FUNCTIONS:
                protected_defs.add(node.name)
        if isinstance(node, ast.ImportFrom) and node.module == CORE_MODULE:
            if core_import is not None:
                raise SystemExit("duplicate core.firmas_utils import")
            core_import = node

    missing = sorted(set(TARGET_FUNCTIONS) - set(target_defs))
    if missing:
        raise SystemExit(f"missing Firmas presentation/state helpers: {missing}")
    if protected_defs != PROTECTED_LOCAL_FUNCTIONS:
        raise SystemExit(f"protected local Firmas invariants missing: {sorted(PROTECTED_LOCAL_FUNCTIONS - protected_defs)}")
    if core_import is None:
        raise SystemExit("core.firmas_utils import missing")

    existing_imports = {alias.asname or alias.name for alias in core_import.names}
    if existing_imports != EXPECTED_EXISTING_IMPORTS:
        raise SystemExit(f"unexpected existing Firmas Core imports: {sorted(existing_imports)}")

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []

    for name in TARGET_FUNCTIONS:
        node = target_defs[name]
        edits.append((node.lineno, node.end_lineno or node.lineno, []))

    final_import = (
        "from core.firmas_utils import "
        + ", ".join(sorted(EXPECTED_FINAL_IMPORTS))
        + "\n"
    )
    edits.append(
        (
            core_import.lineno,
            core_import.end_lineno or core_import.lineno,
            [final_import],
        )
    )

    for start, end, replacement in sorted(edits, reverse=True):
        lines[start - 1 : end] = replacement

    updated = "".join(lines)
    updated_tree = ast.parse(updated)

    remaining_targets = {
        node.name
        for node in updated_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in TARGET_FUNCTIONS
    }
    if remaining_targets:
        raise SystemExit(f"target helpers remained in router: {sorted(remaining_targets)}")

    protected_after = {
        node.name
        for node in updated_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in PROTECTED_LOCAL_FUNCTIONS
    }
    if protected_after != PROTECTED_LOCAL_FUNCTIONS:
        raise SystemExit("protected local Firmas invariant changed")

    imports_after = [
        node
        for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == CORE_MODULE
    ]
    if len(imports_after) != 1:
        raise SystemExit(f"expected one core.firmas_utils import, found {len(imports_after)}")
    imported_after = {alias.asname or alias.name for alias in imports_after[0].names}
    if imported_after != EXPECTED_FINAL_IMPORTS:
        raise SystemExit(f"unexpected final Firmas Core imports: {sorted(imported_after)}")
    if imported_after & PROTECTED_LOCAL_FUNCTIONS:
        raise SystemExit("protected Firmas invariant leaked into Core import")

    TARGET.write_text(updated, encoding="utf-8")
    print("extracted Firmas mail layout, turn rule, and state summary helpers")


if __name__ == "__main__":
    main()
