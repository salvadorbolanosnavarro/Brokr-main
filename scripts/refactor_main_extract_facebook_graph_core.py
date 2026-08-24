#!/usr/bin/env python3
"""Move the shared Meta Graph transport layer out of main.py via bounded AST edits."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

FUNCTIONS = {
    "_fb_appsecret_proof",
    "_fb_parse_error",
    "_fb_friendly_error",
    "_fb_espera_por_uso",
    "_fb_debe_reintentar",
    "_fb_request",
    "_fb_exigir_ok",
    "_fb_get_json",
    "_fb_paginate",
}
ASSIGNMENTS = {
    "FB_API_VERSION",
    "FB_GRAPH",
    "_FB_REINTENTOS",
    "_FB_ESPERA_BASE",
    "_FB_ESPERA_MAX",
    "_FB_CODIGOS_REINTENTABLES",
    "_FB_CODIGOS_TOKEN",
    "_FB_USAR_PROOF",
    "_FB_ERRORES_COMUNES",
}
EXPORTED = sorted(FUNCTIONS | ASSIGNMENTS)
CORE_IMPORT = "from core.facebook_graph import (\n" + "".join(
    f"    {name},\n" for name in EXPORTED
) + ")\n"


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
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id in EXPORTED:
                    counts[child.id] += 1
    return counts


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    function_nodes: list[ast.AST] = []
    for name in FUNCTIONS:
        matches = [
            node for node in body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ]
        if len(matches) != 1:
            raise RuntimeError(f"expected one top-level {name}, found {len(matches)}")
        function_nodes.append(matches[0])

    assignment_nodes: list[ast.AST] = []
    for name in ASSIGNMENTS:
        matches = [node for node in body if name in assigned_names(node)]
        if len(matches) != 1:
            raise RuntimeError(f"expected one top-level assignment for {name}, found {len(matches)}")
        assignment_nodes.append(matches[0])

    selected = function_nodes + assignment_nodes
    selected_ids = {id(node) for node in selected}

    for node in selected:
        if node.end_lineno is None:
            raise RuntimeError(f"selected node at line {node.lineno} missing end_lineno")

    if CORE_IMPORT.strip() in source:
        raise RuntimeError("Facebook Graph Core import already present")

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

    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))

    for name in FUNCTIONS:
        remaining = [
            node for node in out_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        if remaining:
            raise RuntimeError(f"{name} definition remains in main.py")
    for name in ASSIGNMENTS:
        remaining = [node for node in out_tree.body if name in assigned_names(node)]
        if remaining:
            raise RuntimeError(f"{name} assignment remains in main.py")

    if transformed.count("from core.facebook_graph import (") != 1:
        raise RuntimeError("Facebook Graph Core import count mismatch")

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
    print("extracted Facebook Graph transport core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
