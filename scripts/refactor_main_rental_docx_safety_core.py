#!/usr/bin/env python3
"""Validate rental-analysis DOCX archives before python-docx expands them."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"
IMPORT = "from core.documents import validate_docx_archive\n"
IMPORT_ANCHOR = "from core.pdf_store import _pdf_store\n"
EXTRA_OLD = '''        elif "wordprocessingml" in ct or n.endswith(".docx"):
            try:
                from docx import Document as _DocxDocument
'''
EXTRA_NEW = '''        elif "wordprocessingml" in ct or n.endswith(".docx"):
            try:
                validate_docx_archive(raw)
                from docx import Document as _DocxDocument
'''
MAIN_OLD = '''    elif is_docx:
        try:
            from docx import Document as DocxDocument
'''
MAIN_NEW = '''    elif is_docx:
        try:
            validate_docx_archive(content)
            from docx import Document as DocxDocument
'''


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Rental DOCX Core import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if EXTRA_OLD in transformed:
        transformed = transformed.replace(EXTRA_OLD, EXTRA_NEW, 1)
    elif EXTRA_NEW not in transformed:
        raise RuntimeError("Rental supplemental DOCX parser anchor not found")

    if MAIN_OLD in transformed:
        transformed = transformed.replace(MAIN_OLD, MAIN_NEW, 1)
    elif MAIN_NEW not in transformed:
        raise RuntimeError("Rental primary DOCX parser anchor not found")

    if transformed.count("validate_docx_archive(raw)") != 1:
        raise RuntimeError("Unexpected supplemental DOCX validation count")
    if transformed.count("validate_docx_archive(content)") != 1:
        raise RuntimeError("Unexpected primary DOCX validation count")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
