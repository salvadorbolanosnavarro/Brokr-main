#!/usr/bin/env python3
"""Extract pure WhatsApp phone-identity helpers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_identity import es_asesor as _es_asesor, solo_digitos as _solo_digitos\n"
START = "def _solo_digitos(t: str) -> str:\n"
END = "async def _agenda_upsert(user_id: str, numero_id: str, telefono: str,\n"


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
            raise RuntimeError("agenda boundary not found")
        transformed = transformed[:i] + transformed[j:]
    elif "def _es_asesor(" in transformed:
        raise RuntimeError("unexpected phone-identity helper shape")

    for forbidden in ("def _solo_digitos(", "def _es_asesor("):
        if forbidden in transformed:
            raise RuntimeError(f"phone identity helper remains: {forbidden}")

    for required in (
        "async def _agenda_upsert",
        "_es_asesor(numero, wa_dest)",
        "_solo_digitos(wa_id)",
        "_es_asesor(numero, c[\"wa_id\"])",
    ):
        if required not in transformed:
            raise RuntimeError(f"phone identity caller missing: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
