from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TARGET = "_sb_headers"


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))

    funcs = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == TARGET
    ]
    if len(funcs) != 1:
        raise SystemExit(f"expected exactly one {TARGET} definition, found {len(funcs)}")
    target = funcs[0]

    loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == TARGET
    ]
    if loads:
        where = ", ".join(str(node.lineno) for node in loads)
        raise SystemExit(f"{TARGET} is still referenced at line(s): {where}")

    if target.end_lineno is None:
        raise SystemExit(f"missing end_lineno for {TARGET}")

    lines = source.splitlines(keepends=True)
    del lines[target.lineno - 1 : target.end_lineno]
    updated = "".join(lines)
    ast.parse(updated, filename=str(MAIN))
    if updated == source:
        raise SystemExit("transform produced no change")
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
