"""Remove dead FastAPI compatibility imports from main.py after route extraction.

Static-only bounded transform. It refuses to edit main.py if any target name is
still loaded anywhere in the AST, then rewrites exactly the single top-level
``from fastapi import ...`` node.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

DEAD_NAMES = {
    "Query",
    "Request",
    "UploadFile",
    "File",
    "BackgroundTasks",
    "Response",
}
REQUIRED_NAMES = {"FastAPI", "HTTPException"}


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    loaded_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    still_loaded = sorted(DEAD_NAMES & loaded_names)
    if still_loaded:
        raise SystemExit(f"FastAPI cleanup targets still loaded: {still_loaded}")

    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "fastapi" and node.level == 0
    ]
    if len(imports) != 1:
        raise SystemExit(f"expected one top-level fastapi import, found {len(imports)}")

    node = imports[0]
    if node.end_lineno is None:
        raise SystemExit("fastapi import source contract changed")

    imported = {alias.asname or alias.name for alias in node.names}
    missing_required = sorted(REQUIRED_NAMES - imported)
    if missing_required:
        raise SystemExit(f"required FastAPI imports missing before cleanup: {missing_required}")

    present_targets = DEAD_NAMES & imported
    if present_targets != DEAD_NAMES:
        raise SystemExit(
            "dead FastAPI import contract changed: "
            f"expected {sorted(DEAD_NAMES)}, found {sorted(present_targets)}"
        )

    kept = [alias for alias in node.names if (alias.asname or alias.name) not in DEAD_NAMES]
    kept_names = {alias.asname or alias.name for alias in kept}
    if kept_names != REQUIRED_NAMES:
        raise SystemExit(f"unexpected live names in FastAPI import: {sorted(kept_names)}")

    replacement = "from fastapi import FastAPI, HTTPException\n"
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement]
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    final_imports = [
        item
        for item in final_tree.body
        if isinstance(item, ast.ImportFrom) and item.module == "fastapi" and item.level == 0
    ]
    if len(final_imports) != 1:
        raise SystemExit("FastAPI import count changed after cleanup")
    final_names = {alias.asname or alias.name for alias in final_imports[0].names}
    if final_names != REQUIRED_NAMES:
        raise SystemExit(f"FastAPI import cleanup postcondition failed: {sorted(final_names)}")

    MAIN.write_text(updated, encoding="utf-8")
    print("removed dead FastAPI imports from main.py")


if __name__ == "__main__":
    main()
