"""Extract WhatsApp database compatibility adapters into routers.whatsapp_data.

Removes exactly the four top-level legacy async wrappers and replaces them with
one canonical import. The transform is AST-bounded and refuses ambiguous source.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
TARGETS = ("sb_get", "sb_post", "sb_patch", "sb_delete")
IMPORT = "from routers.whatsapp_data import sb_delete, sb_get, sb_patch, sb_post\n"


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp data adapters are already extracted")

    tree = ast.parse(source)
    found: dict[str, ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in TARGETS:
            if node.name in found:
                raise SystemExit(f"duplicate target function: {node.name}")
            found[node.name] = node

    missing = [name for name in TARGETS if name not in found]
    if missing:
        raise SystemExit(f"data adapter source contract changed; missing: {missing}")

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
    lines[insert_line - 1:insert_line - 1] = [IMPORT, "\n"]
    updated = "".join(lines)

    final_tree = ast.parse(updated)
    remaining = {
        node.name
        for node in final_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in TARGETS
    }
    if remaining:
        raise SystemExit(f"legacy data adapters survived: {sorted(remaining)}")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical data import contract changed")
    if "async def _require_user(" not in updated:
        raise SystemExit("data extraction crossed authentication boundary")
    if "data = await get_rows(table, params, timeout=25)" not in updated:
        raise SystemExit("diagnostic direct Core read contract changed")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp data adapters:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
