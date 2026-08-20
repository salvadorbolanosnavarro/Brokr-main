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
OLD_IMPORT = '''from core.easybroker_migration import (\n    MIGRACIONES as _MIGRACIONES,\n    PROGRESO_IMPORT as _PROGRESO_IMPORT,\n    migration_key as _mig_llave,\n    set_import_progress as _prog,\n)\n'''
NEW_IMPORT = 'from core.easybroker_migration import set_import_progress as _prog\n'


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

    if OLD_IMPORT in transformed:
        transformed = transformed.replace(OLD_IMPORT, NEW_IMPORT, 1)

    if MOUNT not in transformed:
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for marker in (
        'async def _job_migracion_eb(',
        '@app.post("/easybroker/migracion/iniciar")',
        '@app.get("/easybroker/migracion/estado")',
        'MIGRACIONES as _MIGRACIONES',
        'PROGRESO_IMPORT as _PROGRESO_IMPORT',
        'migration_key as _mig_llave',
    ):
        if marker in transformed:
            raise RuntimeError(f"EasyBroker migration coordinator residue remains in main: {marker}")
    if NEW_IMPORT not in transformed:
        raise RuntimeError("EasyBroker import progress alias missing from main")
    if '@app.post("/easybroker/import-stats")' not in transformed:
        raise RuntimeError("EasyBroker import-stats endpoint removed unexpectedly")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
