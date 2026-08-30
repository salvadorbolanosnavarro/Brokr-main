from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
RENDERER = ROOT / "routers" / "ficha_pdf_renderer.py"
TARGET = "build_ficha_html"
IMPORT_LINE = "from routers.ficha_pdf_renderer import build_ficha_html\n"


def _find_function(tree: ast.Module, *, where: str) -> ast.FunctionDef:
    found = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == TARGET
    ]
    if len(found) != 1:
        raise SystemExit(f"expected exactly one {TARGET} in {where}, found {len(found)}")
    return found[0]


def _dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    renderer_source = RENDERER.read_text(encoding="utf-8")
    main_tree = ast.parse(source, filename=str(MAIN))
    renderer_tree = ast.parse(renderer_source, filename=str(RENDERER))

    main_fn = _find_function(main_tree, where="main.py")
    renderer_fn = _find_function(renderer_tree, where="ficha_pdf_renderer.py")
    if _dump(main_fn) != _dump(renderer_fn):
        raise SystemExit(f"AST mismatch for {TARGET}")

    for node in main_tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "routers.ficha_pdf_renderer":
            raise SystemExit("ficha_pdf_renderer import already present")

    if main_fn.end_lineno is None:
        raise SystemExit(f"missing end_lineno for {TARGET}")

    lines = source.splitlines(keepends=True)
    start = main_fn.lineno - 1
    end = main_fn.end_lineno
    del lines[start:end]
    lines.insert(start, IMPORT_LINE)

    updated = "".join(lines)
    ast.parse(updated, filename=str(MAIN))
    if updated == source:
        raise SystemExit("transform produced no change")
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
