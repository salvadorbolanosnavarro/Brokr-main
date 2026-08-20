#!/usr/bin/env python3
"""Extract the EasyBroker contact importer from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = '@app.post("/contactos/importar-eb")'
END = '\n\n@app.post("/contactos/importar-archivo")'
MOUNT = '''# Importación de contactos directamente desde EasyBroker.\nfrom routers.easybroker_contact_import import router as easybroker_contact_import_router\napp.include_router(easybroker_contact_import_router)\n\n'''
ANCHOR = '# Estado de migración de fotos EasyBroker.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one EasyBroker contact import route, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("EasyBroker contact import route missing without router mount")

    if MOUNT not in transformed:
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if START in transformed or 'async def importar_contactos_eb(' in transformed:
        raise RuntimeError("EasyBroker contact importer still present in main")
    if '@app.post("/contactos/importar-archivo")' not in transformed:
        raise RuntimeError("file-based contact importer was removed unexpectedly")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
