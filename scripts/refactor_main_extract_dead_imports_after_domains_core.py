from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path("main.py")

TARGETS = {
    "BaseModel",
    "legacy_main_settings",
    "ET",
    "FotoItem",
    "PropData",
}


def _bound_name(alias: ast.alias) -> str:
    return alias.asname or alias.name.split(".", 1)[0]


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
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "pydantic" and [(a.name, a.asname) for a in node.names] == [("BaseModel", None)]:
                exact_imports["BaseModel"] = node
            elif node.module == "core.legacy_main_config" and [(a.name, a.asname) for a in node.names] == [("legacy_main_settings", None)]:
                exact_imports["legacy_main_settings"] = node
            elif node.module == "routers.ficha_pdf_schema" and [(a.name, a.asname) for a in node.names] == [("FotoItem", None), ("PropData", None)]:
                exact_imports["ficha_schema"] = node
        elif isinstance(node, ast.Import):
            if [(a.name, a.asname) for a in node.names] == [("xml.etree.ElementTree", "ET")]:
                exact_imports["ET"] = node

    expected = {"BaseModel", "legacy_main_settings", "ficha_schema", "ET"}
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
