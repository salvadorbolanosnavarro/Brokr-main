#!/usr/bin/env python3
"""Extract behavior-identical WhatsApp agent profile lookup."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
CANONICAL = ROOT / "routers" / "whatsapp_agent_profile.py"
TARGET = "_perfil_agente"
IMPORT_TEXT = "from routers.whatsapp_agent_profile import _perfil_agente\n"


def _function(tree: ast.Module) -> ast.AsyncFunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET
    ]
    if len(matches) != 1:
        raise SystemExit(f"refusing agent-profile extraction: expected one {TARGET}, found {len(matches)}")
    return matches[0]


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL.read_text(encoding="utf-8")
    if IMPORT_TEXT.strip() in source:
        raise SystemExit("WhatsApp agent profile is already extracted")

    source_tree = ast.parse(source, filename=str(SOURCE))
    canonical_tree = ast.parse(canonical, filename=str(CANONICAL))
    source_fn = _function(source_tree)
    canonical_fn = _function(canonical_tree)
    if ast.dump(source_fn, annotate_fields=True, include_attributes=False) != ast.dump(
        canonical_fn, annotate_fields=True, include_attributes=False
    ):
        raise SystemExit("refusing agent-profile extraction: canonical AST differs from whatsapp.py")
    if source_fn.end_lineno is None:
        raise SystemExit("refusing agent-profile extraction: helper lacks end_lineno")

    lines = source.splitlines(keepends=True)
    start, end = source_fn.lineno, source_fn.end_lineno
    lines[start - 1:end] = [IMPORT_TEXT, "\n"]
    updated = "".join(lines)
    updated_tree = ast.parse(updated, filename=str(SOURCE))

    leftovers = [
        node for node in updated_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET
    ]
    if leftovers:
        raise SystemExit("refusing agent-profile extraction: legacy helper survived")
    imports = [
        node for node in updated_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "routers.whatsapp_agent_profile"
    ]
    if len(imports) != 1:
        raise SystemExit("refusing agent-profile extraction: expected one canonical import")
    aliases = [(alias.name, alias.asname) for alias in imports[0].names]
    if aliases != [(TARGET, None)]:
        raise SystemExit(f"refusing agent-profile extraction: unexpected aliases {aliases}")

    SOURCE.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp agent profile helper: _perfil_agente")


if __name__ == "__main__":
    main()
