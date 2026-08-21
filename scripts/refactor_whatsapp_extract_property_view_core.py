#!/usr/bin/env python3
"""Extract pure property presentation helpers from whatsapp.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_property_view import (\n"
    "    _fotos_a_imagenes, _propiedad_para_ficha, _texto_inmueble,\n"
    ")\n"
)
START = "def _texto_inmueble(p: dict) -> str:\n"
END = "\n\nasync def _generar_ficha_pdf(p_ficha: dict) -> tuple[str | None, str | None]:\n"


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
            raise RuntimeError("property-view end anchor not found")
        transformed = transformed[:i] + transformed[j:]
    elif "def _texto_inmueble" in transformed:
        raise RuntimeError("unexpected _texto_inmueble shape")

    for forbidden in (
        "def _texto_inmueble",
        "def _fotos_a_imagenes",
        "def _propiedad_para_ficha",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"property presentation helper remains: {forbidden}")

    if "async def _buscar_inmuebles" not in transformed:
        raise RuntimeError("property search I/O moved unexpectedly")
    if "async def _generar_ficha_pdf" not in transformed:
        raise RuntimeError("PDF I/O moved unexpectedly")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
