#!/usr/bin/env python3
"""Extract the bounded legacy EasyBroker AVM domain from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START = "# ────────────────────────────────────────────\n# AVM — HELPERS\n# ────────────────────────────────────────────\n"
END = "# ────────────────────────────────────────────\n# AVM — CLAUDE AI OPINION DE VALOR\n# ────────────────────────────────────────────\n"
MOUNT = '''# AVM legacy basado en comparables EasyBroker.\nfrom routers.avm_legacy import router as avm_legacy_router\napp.include_router(avm_legacy_router)\n\n'''
ANCHOR = "# Comparables AVM vía Apify/Inmuebles24.\n"


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        start = transformed.index(START)
        end = transformed.find(END, start)
        if end == -1:
            raise RuntimeError("Legacy AVM block end marker not found")
        transformed = transformed[:start] + transformed[end:]
    elif '@app.post("/avm")' in transformed or 'async def calcular_avm(' in transformed:
        raise RuntimeError("Partial legacy AVM extraction detected")

    if MOUNT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Legacy AVM router anchor not found")
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    forbidden = (
        '@app.post("/avm")', 'async def calcular_avm(',
        'async def get_comparables_eb(', 'def ajuste_hedonico(',
        'class AVMRequest(BaseModel):',
    )
    for needle in forbidden:
        if needle in transformed:
            raise RuntimeError(f"Legacy AVM implementation still present in main: {needle}")

    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
