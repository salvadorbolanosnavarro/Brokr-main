"""Extract the bounded pure AI policy block from whatsapp.py.

The target functions already live canonically in routers.whatsapp_policy. This
transform removes exactly those four top-level legacy definitions and replaces
them with one explicit import at the position of the first removed definition.
The edit is AST-bounded and refuses ambiguous/already-migrated source.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
TARGETS = ("_parse_ts", "_modo_conv", "_conv_pausada", "_ia_decide")
IMPORT = "from routers.whatsapp_policy import _conv_pausada, _ia_decide, _modo_conv, _parse_ts\n"


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp policy is already extracted")

    tree = ast.parse(source)
    found: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS:
            if node.name in found:
                raise SystemExit(f"duplicate target function: {node.name}")
            found[node.name] = node

    missing = [name for name in TARGETS if name not in found]
    if missing:
        raise SystemExit(f"policy source contract changed; missing: {missing}")

    spans: list[tuple[int, int]] = []
    for name in TARGETS:
        node = found[name]
        if node.end_lineno is None:
            raise SystemExit(f"missing end_lineno for {name}")
        spans.append((node.lineno, node.end_lineno))

    insert_line = min(start for start, _ in spans)
    lines = source.splitlines(keepends=True)

    for start, end in sorted(spans, reverse=True):
        lines[start - 1:end] = []

    removed_before_insert = sum(
        (end - start + 1) for start, end in spans if start < insert_line
    )
    adjusted_insert = insert_line - removed_before_insert
    lines[adjusted_insert - 1:adjusted_insert - 1] = [IMPORT, "\n"]
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    remaining = {
        node.name
        for node in final_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in TARGETS
    }
    if remaining:
        raise SystemExit(f"legacy policy definitions survived: {sorted(remaining)}")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical policy import contract changed")
    if "async def _pausar_por_respuesta_manual(" not in updated:
        raise SystemExit("policy extraction crossed its bounded successor")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp AI policy:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
