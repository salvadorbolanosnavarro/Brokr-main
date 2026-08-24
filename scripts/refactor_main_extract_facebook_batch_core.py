#!/usr/bin/env python3
"""Move the shared Meta Graph batch helper out of main.py via bounded AST edits."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
NAME = "_fb_batch"


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(deco.lineno for deco in node.decorator_list)
    return min(starts)


def loaded_count(nodes: list[ast.AST]) -> int:
    count = 0
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id == NAME:
                count += 1
    return count


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    functions = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == NAME
    ]
    if len(functions) != 1:
        raise RuntimeError(f"expected one top-level {NAME}, found {len(functions)}")
    func = functions[0]
    if [arg.arg for arg in func.args.args] != [
        "client", "token", "peticiones", "timeout", "espera_base", "espera_max"
    ]:
        raise RuntimeError("unexpected _fb_batch signature")
    func_src = ast.get_source_segment(source, func) or ""
    for fragment in (
        "range(0, len(peticiones), 50)",
        'data={"batch": json.dumps(lote)',
        '"include_headers": "false"',
        '_fb_friendly_error(r.text if r is not None else "", "Batch")',
        '"Respuesta ilegible de Facebook"',
        '"Respuesta inesperada de Facebook"',
        '"Elemento inesperado"',
        'int(res.get("code") or 0)',
    ):
        if fragment not in func_src:
            raise RuntimeError(f"missing expected batch behavior: {fragment}")

    imports = [
        node for node in body
        if isinstance(node, ast.ImportFrom) and node.module == "core.facebook_graph"
    ]
    if len(imports) != 1:
        raise RuntimeError(f"expected one core.facebook_graph import, found {len(imports)}")
    graph_import = imports[0]
    imported = [alias.name for alias in graph_import.names]
    if NAME in imported:
        raise RuntimeError("_fb_batch already imported from Core")
    if "_fb_request" not in imported or "_fb_paginate" not in imported:
        raise RuntimeError("unexpected core.facebook_graph import shape")
    if func.end_lineno is None or graph_import.end_lineno is None:
        raise RuntimeError("AST nodes missing end_lineno")

    outside_before = loaded_count([node for node in body if node is not func])
    lines = source.splitlines(keepends=True)
    edits = [
        (node_start(func) - 1, func.end_lineno, []),
        (graph_import.end_lineno - 1, graph_import.end_lineno - 1, ["    _fb_batch,\n"]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))

    if any(isinstance(node, ast.AsyncFunctionDef) and node.name == NAME for node in out_tree.body):
        raise RuntimeError("_fb_batch definition remains in main.py")
    out_imports = [
        node for node in out_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.facebook_graph"
    ]
    if len(out_imports) != 1:
        raise RuntimeError("core.facebook_graph import count changed")
    if sum(alias.name == NAME for alias in out_imports[0].names) != 1:
        raise RuntimeError("_fb_batch Core import count mismatch")
    outside_after = loaded_count(out_tree.body)
    if outside_after != outside_before:
        raise RuntimeError(
            f"external _fb_batch caller count changed: before={outside_before} after={outside_after}"
        )
    if transformed == source:
        raise RuntimeError("transform produced no changes")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted Facebook Graph batch core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
