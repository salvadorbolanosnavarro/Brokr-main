#!/usr/bin/env python3
"""Extract the bounded Claude AVM opinion endpoint from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START = "# ────────────────────────────────────────────\n# AVM — CLAUDE AI OPINION DE VALOR\n# ────────────────────────────────────────────\n"
END = "# ────────────────────────────────────────────\n# AVM — OPINIÓN DE VALOR CON INVESTIGACIÓN CONTROLADA DE COMPARABLES\n# ────────────────────────────────────────────\n"
MOUNT = '''# Opinión de valor AVM vía Claude.\nfrom routers.avm_claude import router as avm_claude_router\napp.include_router(avm_claude_router)\n\n'''
ANCHOR = "# Comparables AVM vía Apify/Inmuebles24.\n"


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        start = transformed.index(START)
        end = transformed.find(END, start)
        if end == -1:
            raise RuntimeError("Claude AVM block end marker not found")
        transformed = transformed[:start] + transformed[end:]
    elif '@app.post("/api/avm-claude")' in transformed or 'async def avm_claude(' in transformed:
        raise RuntimeError("Partial Claude AVM extraction detected")

    if MOUNT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Claude AVM router anchor not found")
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for needle in ('@app.post("/api/avm-claude")', 'async def avm_claude(', 'class AvmClaudeRequest(BaseModel):'):
        if needle in transformed:
            raise RuntimeError(f"Claude AVM implementation still present in main: {needle}")

    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
