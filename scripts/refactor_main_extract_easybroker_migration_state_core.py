#!/usr/bin/env python3
"""Move EasyBroker migration state/progress primitives from main.py to Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = '_MIGRACIONES: dict = {}   # org o user -> estado del trabajo'
END = '\n\nasync def _job_migracion_eb(llave: str, auth_header: str):'
IMPORT = '''from core.easybroker_migration import (\n    MIGRACIONES as _MIGRACIONES,\n    PROGRESO_IMPORT as _PROGRESO_IMPORT,\n    migration_key as _mig_llave,\n    set_import_progress as _prog,\n)\n'''
ANCHOR = 'from core.easybroker_mapping import _EB_LIMITE_PROPIEDADES, _EB_STATUS_DEFAULT, _EB_STATUS_MAP, _eb_to_brokr\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one EasyBroker migration state block, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif IMPORT not in transformed:
        raise RuntimeError("EasyBroker migration state block missing without Core import")

    if IMPORT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("EasyBroker Core import anchor not found")
        transformed = transformed.replace(ANCHOR, ANCHOR + IMPORT, 1)

    for local_def in (
        '_MIGRACIONES: dict = {}',
        '_PROGRESO_IMPORT: dict = {}',
        'def _prog(user_id: str, texto: str):',
        'def _mig_llave(org_id, user_id):',
    ):
        if local_def in transformed:
            raise RuntimeError(f"legacy EasyBroker migration primitive remains in main: {local_def}")

    if transformed.count('_prog(') < 3:
        raise RuntimeError("expected EasyBroker import progress consumers to remain")
    if transformed.count('_mig_llave(') < 2:
        raise RuntimeError("expected EasyBroker migration key consumers to remain")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
