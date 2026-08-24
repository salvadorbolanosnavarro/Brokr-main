#!/usr/bin/env python3
"""Move the server-only Facebook integration row reader out of main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
HELPER_NAME = "_fb_get_meta_row"
CORE_IMPORT = (
    "from core.facebook_connection_store import "
    "get_facebook_meta_row as _fb_get_meta_row\n"
)


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    helpers = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == HELPER_NAME
    ]
    if len(helpers) != 1:
        raise RuntimeError(f"expected one {HELPER_NAME}, found {len(helpers)}")
    helper = helpers[0]
    if helper.end_lineno is None:
        raise RuntimeError(f"{HELPER_NAME} missing end_lineno")
    if helper.decorator_list:
        raise RuntimeError(f"{HELPER_NAME} unexpectedly has decorators")

    names = {
        node.id for node in ast.walk(helper)
        if isinstance(node, ast.Name)
    }
    for required in {"get_rows", "descifrar_secreto", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"}:
        if required not in names:
            raise RuntimeError(f"{HELPER_NAME} no longer references {required}")

    loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == HELPER_NAME
    ]
    if len(loads) < 2:
        raise RuntimeError(
            f"expected {HELPER_NAME} to remain a shared helper with multiple callers, found {len(loads)} loads"
        )

    if CORE_IMPORT.strip() in source:
        raise RuntimeError("Facebook connection store import already present")

    app_assigns = [
        node for node in body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_assigns) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(app_assigns)}")
    app_assign = app_assigns[0]

    lines = source.splitlines(keepends=True)
    edits = [
        (node_start(helper) - 1, helper.end_lineno, []),
        (app_assign.lineno - 1, app_assign.lineno - 1, [CORE_IMPORT, "\n"]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)

    out_tree = ast.parse(transformed, filename=str(MAIN))
    remaining_defs = [
        node for node in out_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == HELPER_NAME
    ]
    if remaining_defs:
        raise RuntimeError(f"{HELPER_NAME} definition remains in main.py")
    if transformed.count(CORE_IMPORT.strip()) != 1:
        raise RuntimeError("Facebook connection store import count mismatch")

    remaining_loads = [
        node for node in ast.walk(out_tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == HELPER_NAME
    ]
    if len(remaining_loads) != len(loads):
        raise RuntimeError(
            f"caller count changed while extracting {HELPER_NAME}: "
            f"before={len(loads)} after={len(remaining_loads)}"
        )

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook connection store read helper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
