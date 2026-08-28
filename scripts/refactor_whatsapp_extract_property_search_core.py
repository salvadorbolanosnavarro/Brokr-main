#!/usr/bin/env python3
"""Extract behavior-identical WhatsApp property search from whatsapp.py.

The transform compares the executable AST of _buscar_inmuebles with the
canonical implementation before making any edit. It then removes exactly that
one top-level helper and replaces it with one canonical import.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_property_search.py"
TARGET = "_buscar_inmuebles"
IMPORT_TEXT = "from routers.whatsapp_property_search import _buscar_inmuebles\n"


def _top_level_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing property-search extraction: expected one {name}, found {len(matches)}")
    return matches[0]


def _shape(node: ast.AsyncFunctionDef) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")

    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp property search is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _top_level_function(source_tree, TARGET)
    canonical_fn = _top_level_function(canonical_tree, TARGET)

    if _shape(source_fn) != _shape(canonical_fn):
        raise SystemExit("refusing property-search extraction: canonical AST differs from whatsapp.py")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing property-search extraction: helper lacks end_lineno")

    lines = source.splitlines(keepends=True)
    start = source_fn.lineno
    end = source_fn.end_lineno
    replacement = [IMPORT_TEXT, "\n"]
    lines[start - 1:end] = replacement
    updated = "".join(lines)

    updated_tree = ast.parse(updated, filename=str(SOURCE))
    leftovers = [
        node for node in updated_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET
    ]
    if leftovers:
        raise SystemExit("refusing property-search extraction: legacy helper survived")

    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_property_search"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing property-search extraction: expected one canonical import")
    aliases = [(alias.name, alias.asname) for alias in imports[0].names]
    if aliases != [(TARGET, None)]:
        raise SystemExit(f"refusing property-search extraction: unexpected import aliases {aliases}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp property search helper: _buscar_inmuebles")


if __name__ == "__main__":
    main()
