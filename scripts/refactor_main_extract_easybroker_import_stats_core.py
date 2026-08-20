#!/usr/bin/env python3
"""Extract EasyBroker historical lead import from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = '@app.post("/easybroker/import-stats")'
END = '\n\n# ─────────────────────────────────────────────\n# ADMIN'
MOUNT = '''# Importación del historial de leads de EasyBroker.\nfrom routers.easybroker_import_stats import router as easybroker_import_stats_router\napp.include_router(easybroker_import_stats_router)\n\n'''
ANCHOR = '# Coordinador de migración completa EasyBroker.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one EasyBroker import-stats route, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("EasyBroker import-stats route missing without router mount")

    if MOUNT not in transformed:
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if START in transformed or 'async def easybroker_import_stats(' in transformed:
        raise RuntimeError("EasyBroker import-stats implementation still present in main")
    if '# ADMIN' not in transformed:
        raise RuntimeError("admin section removed unexpectedly")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
