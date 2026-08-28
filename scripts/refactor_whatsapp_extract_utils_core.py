"""Extract bounded pure utility helpers from whatsapp.py.

The canonical implementations live in routers.whatsapp_utils. This transform
removes exactly four top-level legacy functions and aliases the canonical public
names back to their legacy private names so all callers remain unchanged.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
TARGETS = ("_normaliza_mx", "_money", "_parsear_presupuesto", "_in_filter")
IMPORT = (
    "from routers.whatsapp_utils import in_filter as _in_filter, money as _money, "
    "normaliza_mx as _normaliza_mx, parsear_presupuesto as _parsear_presupuesto\n"
)


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp utilities are already extracted")

    tree = ast.parse(source)
    found: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS:
            if node.name in found:
                raise SystemExit(f"duplicate target function: {node.name}")
            found[node.name] = node

    missing = [name for name in TARGETS if name not in found]
    if missing:
        raise SystemExit(f"utility source contract changed; missing: {missing}")

    spans = []
    for name in TARGETS:
        node = found[name]
        if node.end_lineno is None:
            raise SystemExit(f"missing end_lineno for {name}")
        spans.append((node.lineno, node.end_lineno, name))

    first_start = min(start for start, _, _ in spans)
    lines = source.splitlines(keepends=True)
    for start, end, _name in sorted(spans, reverse=True):
        replacement = [IMPORT, "\n"] if start == first_start else []
        lines[start - 1:end] = replacement
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    remaining = {
        node.name
        for node in final_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS
    }
    if remaining:
        raise SystemExit(f"legacy utility definitions survived: {sorted(remaining)}")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical utility import contract changed")
    if "async def _require_user(" not in updated:
        raise SystemExit("utility extraction crossed authentication boundary")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp utilities:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
