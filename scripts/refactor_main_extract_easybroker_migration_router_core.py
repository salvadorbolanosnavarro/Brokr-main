#!/usr/bin/env python3
"""Extract the EasyBroker migration coordinator from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'async def _job_migracion_eb(llave: str, auth_header: str):'
END = '\n\n@app.post("/easybroker/import-stats")'
MOUNT = '''# Coordinador de migración completa EasyBroker.\nfrom routers.easybroker_migration import router as easybroker_migration_router\napp.include_router(easybroker_migration_router)\n\n'''
ANCHOR = '# Importación de contactos directamente desde EasyBroker.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one EasyBroker migration coordinator, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("EasyBroker migration coordinator missing without router mount")

    if MOUNT not in transformed:
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for marker in (
        'async def _job_migracion_eb(',
        '@app.post("/easybroker/migracion/iniciar")',
        '@app.get("/easybroker/migracion/estado")',
    ):
        if marker in transformed:
            raise RuntimeError(f"EasyBroker migration coordinator remains in main: {marker}")
    if '@app.post("/easybroker/import-stats")' not in transformed:
        raise RuntimeError("EasyBroker import-stats endpoint removed unexpectedly")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
