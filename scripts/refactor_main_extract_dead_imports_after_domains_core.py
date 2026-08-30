from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path("main.py")

TARGETS = {
    "BaseModel",
    "ET",
    "FotoItem",
    "PropData",
}


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)

    loaded = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    still_used = sorted(TARGETS & loaded)
    if still_used:
        raise SystemExit(f"refusing to remove still-used imports: {still_used}")

    exact_imports: dict[str, ast.stmt] = {}
    guarded_legacy_import = False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            names = [(a.name, a.asname) for a in node.names]
            if node.module == "pydantic" and names == [("BaseModel", None)]:
                exact_imports["BaseModel"] = node
            elif node.module == "core.legacy_main_config" and names == [("legacy_main_settings", None)]:
                guarded_legacy_import = True
            elif node.module == "routers.ficha_pdf_schema" and names == [("FotoItem", None), ("PropData", None)]:
                exact_imports["ficha_schema"] = node
        elif isinstance(node, ast.Import):
            if [(a.name, a.asname) for a in node.names] == [("xml.etree.ElementTree", "ET")]:
                exact_imports["ET"] = node

    if not guarded_legacy_import:
        raise SystemExit("guarded legacy_main_settings import must remain in main.py")

    expected = {"BaseModel", "ficha_schema", "ET"}
    if set(exact_imports) != expected:
        raise SystemExit(
            f"exact dead-import shape changed: found={sorted(exact_imports)} expected={sorted(expected)}"
        )

    spans = sorted(
        ((node.lineno, node.end_lineno) for node in exact_imports.values()),
        reverse=True,
    )
    lines = source.splitlines(keepends=True)
    for start, end in spans:
        del lines[start - 1 : end]

    updated = "".join(lines)
    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
