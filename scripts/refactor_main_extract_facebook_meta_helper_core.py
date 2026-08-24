#!/usr/bin/env python3
"""Move the strict Facebook metadata reader out of main.py via bounded AST edits."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT = "from core.facebook_connection_store import get_facebook_meta as _get_fb_meta\n"
NAME = "_get_fb_meta"


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
    funcs = [node for node in body if isinstance(node, ast.AsyncFunctionDef) and node.name == NAME]
    if len(funcs) != 1:
        raise RuntimeError(f"expected one top-level {NAME}, found {len(funcs)}")
    func = funcs[0]
    if [arg.arg for arg in func.args.args] != ["user_id"]:
        raise RuntimeError("unexpected _get_fb_meta signature")
    src = ast.get_source_segment(source, func) or ""
    for fragment in (
        '"user_integrations"',
        '"provider": "eq.facebook"',
        '"select": "meta"',
        'except httpx.HTTPStatusError',
        'status_code=400, detail="Facebook no conectado"',
        'meta["user_token"] = descifrar_secreto(meta["user_token"])',
        "return meta",
    ):
        if fragment not in src:
            raise RuntimeError(f"missing expected _get_fb_meta behavior: {fragment}")
    if IMPORT.strip() in source:
        raise RuntimeError("strict Facebook metadata Core import already present")

    apps = [
        node for node in body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(apps)}")

    outside_before = loaded_count([node for node in body if node is not func])
    if func.end_lineno is None:
        raise RuntimeError("_get_fb_meta missing end_lineno")
    lines = source.splitlines(keepends=True)
    edits = [
        (func.lineno - 1, func.end_lineno, []),
        (apps[0].lineno - 1, apps[0].lineno - 1, [IMPORT, "\n"]),
    ]
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)
    out_tree = ast.parse(transformed, filename=str(MAIN))
    if any(isinstance(node, ast.AsyncFunctionDef) and node.name == NAME for node in out_tree.body):
        raise RuntimeError("_get_fb_meta definition remains in main.py")
    if transformed.count(IMPORT.strip()) != 1:
        raise RuntimeError("strict Facebook metadata Core import count mismatch")
    outside_after = loaded_count(out_tree.body)
    if outside_after != outside_before:
        raise RuntimeError(
            f"external _get_fb_meta caller count changed: before={outside_before} after={outside_after}"
        )
    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted strict Facebook metadata helper core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
