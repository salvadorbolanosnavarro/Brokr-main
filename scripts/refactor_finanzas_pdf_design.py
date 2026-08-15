#!/usr/bin/env python3
"""Move Finanzas PDF palette to the canonical Broquer design tokens."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "finanzas.py"

OLD_IMPORT = '''from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.storage import create_signed_object_url, delete_object, upload_object
'''
NEW_IMPORT = '''from core.database import delete_rows, get_rows, patch_rows, post_rows
from core.design import pdf_palette
from core.storage import create_signed_object_url, delete_object, upload_object
'''

OLD_TOKENS = '''# Tokens mínimos para el impreso. Duplicado consciente de brokr-theme.css:
# el router es autónomo y un PDF no puede quedarse sin colores si el theme
# no está en el disco del contenedor.
_PDF_TOKENS = {
    "ink": "#0B0B0F", "navy": "#05203C", "blue": "#0A5DE0",
    "mute": "#5A6478", "line": "#E4E8F0", "paper2": "#F6F8FB",
    "green": "#12A150", "orange": "#F7740D",
}
'''
NEW_TOKENS = '''# PDF colors are resolved from the executable canonical theme. The report
# renderer keeps semantic names while color values live only in brokr-theme.css.
_PDF_TOKENS = pdf_palette()
'''


def transform(text: str) -> str:
    if "from core.design import pdf_palette" in text:
        raise RuntimeError("Finanzas PDF design refactor already appears applied")
    if text.count(OLD_IMPORT) != 1:
        raise RuntimeError("Finanzas design import block does not match reviewed source")
    if text.count(OLD_TOKENS) != 1:
        raise RuntimeError("Finanzas copied PDF palette does not match reviewed source")
    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)
    return text.replace(OLD_TOKENS, NEW_TOKENS, 1)


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    compile(updated, "routers/finanzas.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
