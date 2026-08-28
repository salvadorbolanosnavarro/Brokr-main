"""Extract bounded timezone/calendar helpers from whatsapp.py.

The canonical implementations live in routers.whatsapp_time. This transform
removes exactly five top-level legacy functions and aliases the canonical public
names back to their legacy private names so existing callers remain unchanged.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
TARGETS = ("_now", "_hora_local", "_fmt_fecha_larga", "_fecha_hora_utc_iso", "_construir_ics")
IMPORT = (
    "from routers.whatsapp_time import construir_ics as _construir_ics, "
    "fecha_hora_utc_iso as _fecha_hora_utc_iso, fmt_fecha_larga as _fmt_fecha_larga, "
    "hora_local as _hora_local, now_iso as _now\n"
)


def main() -> None:
    source = WHATSAPP.read_text(encoding="utf-8")
    if IMPORT.strip() in source:
        raise SystemExit("WhatsApp time helpers are already extracted")

    tree = ast.parse(source)
    found: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS:
            if node.name in found:
                raise SystemExit(f"duplicate target function: {node.name}")
            found[node.name] = node

    missing = [name for name in TARGETS if name not in found]
    if missing:
        raise SystemExit(f"time source contract changed; missing: {missing}")

    spans: list[tuple[int, int, str]] = []
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
        raise SystemExit(f"legacy time definitions survived: {sorted(remaining)}")
    if updated.count(IMPORT.strip()) != 1:
        raise SystemExit("canonical time import contract changed")
    if "async def _pausar_por_respuesta_manual(" not in updated:
        raise SystemExit("time extraction crossed policy boundary")
    if "async def _require_user(" not in updated:
        raise SystemExit("time extraction crossed authentication boundary")

    WHATSAPP.write_text(updated, encoding="utf-8")
    print("extracted WhatsApp time helpers:", ", ".join(TARGETS))


if __name__ == "__main__":
    main()
