#!/usr/bin/env python3
"""Extract pure WhatsApp statistics aggregation from whatsapp.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_stats import _agrega_ventana, _dt, _mediana\n"
START = "def _dt(valor) -> datetime | None:\n"
END = "\n\n@router.get(\"/estadisticas\")\n"


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if START in transformed:
        i = transformed.find(START)
        j = transformed.find(END, i)
        if j < 0:
            raise RuntimeError("statistics endpoint anchor not found")
        transformed = transformed[:i] + transformed[j:]
    elif "def _dt(valor)" in transformed:
        raise RuntimeError("unexpected statistics helper shape")

    for forbidden in ("def _dt(valor)", "def _mediana(nums", "def _agrega_ventana("):
        if forbidden in transformed:
            raise RuntimeError(f"statistics helper remains in whatsapp.py: {forbidden}")

    for required in (
        "async def _sb_diag",
        "async def _sb_get_paginado",
        '@router.get("/estadisticas")',
    ):
        if required not in transformed:
            raise RuntimeError(f"statistics I/O moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
