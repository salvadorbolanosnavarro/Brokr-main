#!/usr/bin/env python3
"""Validate uploaded Machotes DOCX archives before parsing them."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "machotes.py"
IMPORT = "from core.documents import UnsafeDocument, validate_docx_archive\n"
IMPORT_ANCHOR = "from core.database import delete_rows, get_rows, patch_rows, post_rows\n"
ANCHOR = '    if not (file.filename or "").lower().endswith(".docx"):\n        raise HTTPException(status_code=400, detail="Solo aceptamos archivos .docx (Word).")\n'
GUARD = (
    '    try:\n'
    '        validate_docx_archive(content)\n'
    '    except UnsafeDocument as exc:\n'
    '        raise HTTPException(\n'
    '            status_code=400,\n'
    '            detail="El archivo .docx está corrupto o se expande más de lo permitido.",\n'
    '        ) from exc\n'
)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Machotes Core database import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if GUARD not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Machotes DOCX validation anchor not found")
        transformed = transformed.replace(ANCHOR, ANCHOR + GUARD, 1)

    if transformed.count("validate_docx_archive(content)") != 1:
        raise RuntimeError("Unexpected Machotes DOCX validation count")
    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
