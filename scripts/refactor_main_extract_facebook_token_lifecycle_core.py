#!/usr/bin/env python3
"""Move shared Facebook token lifecycle primitives out of main.py via bounded AST edits."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

LIFETIME_NAME = "_FB_TOKEN_VIDA_DEFECTO"
DEBUG_NAME = "_fb_debug_token"
EXPORTED = {LIFETIME_NAME, DEBUG_NAME}
CORE_IMPORT = (
    "from core.facebook_token_lifecycle import "
    "(FB_TOKEN_DEFAULT_LIFETIME_SECONDS as _FB_TOKEN_VIDA_DEFECTO, "
    "debug_facebook_token as _fb_debug_token)\n"
)


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def assigned_names(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Assign):
        return set()
    return {
        target.id
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def loaded_counts(nodes: list[ast.AST]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in nodes:
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in EXPORTED
            ):
                counts[child.id] += 1
    return counts


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    lifetime_nodes = [node for node in body if LIFETIME_NAME in assigned_names(node)]
    if len(lifetime_nodes) != 1:
        raise RuntimeError(
            f"expected one top-level assignment for {LIFETIME_NAME}, found {len(lifetime_nodes)}"
        )
    lifetime_node = lifetime_nodes[0]
    if ast.unparse(lifetime_node.value) != "60 * 24 * 3600":
        raise RuntimeError("unexpected Facebook default token lifetime expression")

    debug_nodes = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == DEBUG_NAME
    ]
    if len(debug_nodes) != 1:
        raise RuntimeError(f"expected one top-level {DEBUG_NAME}, found {len(debug_nodes)}")
    debug_node = debug_nodes[0]
    if [arg.arg for arg in debug_node.args.args] != ["client", "token"]:
        raise RuntimeError("unexpected _fb_debug_token signature")

    debug_text = ast.get_source_segment(source, debug_node) or ""
    required_fragments = (
        '"debug_token"',
        '"input_token": token',
        '"access_token": f"{FB_APP_ID}|{FB_APP_SECRET}"',
        "reintentos=2",
        "if r is None or r.status_code != 200:",
        'return (r.json() or {}).get("data") or {}',
        "except Exception:",
    )
    missing = [fragment for fragment in required_fragments if fragment not in debug_text]
    if missing:
        raise RuntimeError(f"unexpected _fb_debug_token body; missing {missing}")

    if CORE_IMPORT.strip() in source:
        raise RuntimeError("Facebook token lifecycle Core import already present")

    selected = [lifetime_node, debug_node]
    selected_ids = {id(node) for node in selected}
    for node in selected:
        if node.end_lineno is None:
            raise RuntimeError(f"selected node at line {node.lineno} missing end_lineno")

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

    outside_before = loaded_counts([node for node in body if id(node) not in selected_ids])

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    for node in selected:
        edits.append((node_start(node) - 1, node.end_lineno, []))
    edits.append((app_assign.lineno - 1, app_assign.lineno - 1, [CORE_IMPORT, "\n"]))

    for start, end, replacement in sorted(
        edits, key=lambda item: (item[0], item[1]), reverse=True
    ):
        lines[start:end] = replacement

    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))

    if any(LIFETIME_NAME in assigned_names(node) for node in out_tree.body):
        raise RuntimeError(f"{LIFETIME_NAME} assignment remains in main.py")
    if any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == DEBUG_NAME
        for node in out_tree.body
    ):
        raise RuntimeError(f"{DEBUG_NAME} definition remains in main.py")
    if transformed.count("from core.facebook_token_lifecycle import ") != 1:
        raise RuntimeError("Facebook token lifecycle Core import count mismatch")

    outside_after = loaded_counts(out_tree.body)
    for name in EXPORTED:
        if outside_after[name] != outside_before[name]:
            raise RuntimeError(
                f"external caller count changed for {name}: "
                f"before={outside_before[name]} after={outside_after[name]}"
            )

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook token lifecycle core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
