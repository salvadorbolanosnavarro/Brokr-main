from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCHEMA = ROOT / "routers" / "ficha_pdf_schema.py"
TARGETS = ("FotoItem", "PropData")
IMPORT_LINE = "from routers.ficha_pdf_schema import FotoItem, PropData\n"


def _class_map(tree: ast.Module) -> dict[str, ast.ClassDef]:
    found: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in TARGETS:
            if node.name in found:
                raise SystemExit(f"duplicate top-level class: {node.name}")
            found[node.name] = node
    return found


def _dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    schema_source = SCHEMA.read_text(encoding="utf-8")
    main_tree = ast.parse(source, filename=str(MAIN))
    schema_tree = ast.parse(schema_source, filename=str(SCHEMA))

    main_classes = _class_map(main_tree)
    schema_classes = _class_map(schema_tree)
    for name in TARGETS:
        if name not in main_classes:
            raise SystemExit(f"missing {name} in main.py")
        if name not in schema_classes:
            raise SystemExit(f"missing {name} in ficha_pdf_schema.py")
        if _dump(main_classes[name]) != _dump(schema_classes[name]):
            raise SystemExit(f"AST mismatch for {name}")

    for node in main_tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "routers.ficha_pdf_schema":
            raise SystemExit("ficha_pdf_schema import already present")

    lines = source.splitlines(keepends=True)
    spans = []
    for name in TARGETS:
        node = main_classes[name]
        if node.end_lineno is None:
            raise SystemExit(f"missing end_lineno for {name}")
        spans.append((node.lineno - 1, node.end_lineno))
    spans.sort()

    first_start = spans[0][0]
    for start, end in reversed(spans):
        del lines[start:end]
    lines.insert(first_start, IMPORT_LINE)

    updated = "".join(lines)
    ast.parse(updated, filename=str(MAIN))
    if updated == source:
        raise SystemExit("transform produced no change")
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
