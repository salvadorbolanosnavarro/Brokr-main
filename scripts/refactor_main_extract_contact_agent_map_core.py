#!/usr/bin/env python3
"""Move the shared contact-import agent map helper from main.py to Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'async def _mapa_agentes_org(org_id: str, user_id: str) -> dict:'
END = '\n\n\n@app.post("/contactos/importar-eb")'
IMPORT = 'from core.contact_import import map_org_agents as _mapa_agentes_org\n'
ANCHOR = 'from core.cache import cache_get, cache_set\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one contact agent map helper, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif IMPORT not in transformed:
        raise RuntimeError("contact agent map helper missing without Core import")

    if IMPORT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Core import anchor not found")
        transformed = transformed.replace(ANCHOR, ANCHOR + IMPORT, 1)

    if START in transformed:
        raise RuntimeError("contact agent map helper still present in main")
    if transformed.count('_mapa_agentes_org(') != 2:
        raise RuntimeError(
            f"Expected two contact-import consumers after extraction, found {transformed.count('_mapa_agentes_org(')}"
        )
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
