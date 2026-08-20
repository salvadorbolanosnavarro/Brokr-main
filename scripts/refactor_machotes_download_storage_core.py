#!/usr/bin/env python3
"""Delegate Machotes private template downloads to canonical core.storage."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "machotes.py"
IMPORT = "from core.storage import download_object\n"
IMPORT_ANCHOR = "from core.executors import _thread_pool\n"
BLOCK_START = "async def _descargar_plantilla(storage_path: str) -> bytes:\n"
BLOCK_END = "async def _subir_a_storage(client: httpx.AsyncClient, path: str, content: bytes):\n"
REPLACEMENT = '''async def _descargar_plantilla(storage_path: str) -> bytes:\n    try:\n        return await download_object(MACHOTES_BUCKET, storage_path, timeout=30)\n    except httpx.HTTPStatusError:\n        raise HTTPException(status_code=500, detail="No se pudo leer el archivo de tu machote.")\n\n\n'''


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Machotes storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if BLOCK_START in transformed:
        start = transformed.index(BLOCK_START)
        end = transformed.find(BLOCK_END, start)
        if end == -1:
            raise RuntimeError("Machotes upload helper anchor not found")
        transformed = transformed[:start] + REPLACEMENT + transformed[end:]
    elif "return await download_object(MACHOTES_BUCKET, storage_path, timeout=30)" not in transformed:
        raise RuntimeError("Unknown Machotes download state")

    if '/storage/v1/object/{MACHOTES_BUCKET}/{storage_path}' in transformed:
        raise RuntimeError("Direct Machotes template download URL remains")
    if "async def _subir_a_storage(" not in transformed:
        raise RuntimeError("Machotes upload behavior moved unexpectedly")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    SOURCE.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
