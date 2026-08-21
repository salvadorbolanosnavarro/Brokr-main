#!/usr/bin/env python3
"""Extract WhatsApp Cloud API transport helpers from the root monolith."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_cloud_api import (\n"
    "    descargar_media as _descargar_media, marcar_leido as _wa_marcar_leido,\n"
    "    revisar_token as _revisar_token, send_document as _wa_send_document,\n"
    "    send_document_link as _wa_send_document_link, send_image as _wa_send_image,\n"
    "    send_text as _wa_send_text, send_text_detallado as _wa_send_text_detallado,\n"
    ")\n"
)
REMOVE = {
    "_revisar_token",
    "_wa_send_text_detallado",
    "_wa_send_text",
    "_wa_marcar_leido",
    "_descargar_media",
    "_wa_send_image",
    "_wa_send_document",
    "_wa_send_document_link",
}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    for node in tree.body:
        if getattr(node, "name", None) not in REMOVE:
            continue
        start = node.lineno - 1
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(d.lineno for d in decorators) - 1
        end = node.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    transformed = _remove_nodes(transformed)

    for forbidden in (
        "async def _revisar_token",
        "async def _wa_send_text_detallado",
        "async def _wa_send_text(",
        "async def _wa_marcar_leido",
        "async def _descargar_media",
        "async def _wa_send_image",
        "async def _wa_send_document(",
        "async def _wa_send_document_link",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"Cloud API helper remains: {forbidden}")

    for required in (
        "async def _transcribir_audio",
        "async def _describir_imagen",
        "async def _guardar_archivo",
        "_wa_send_text_detallado(numero, contacto.get(\"wa_id\"), texto)",
        "_wa_marcar_leido(numero_rows[0], wamid, escribiendo=False)",
        "_descargar_media(numero, media_id)",
        "_wa_send_document(numero, contacto.get(\"wa_id\"), ics.encode(\"utf-8\")",
        "_wa_send_image(numero, item[\"wa_id\"], foto",
    ):
        if required not in transformed:
            raise RuntimeError(f"Cloud API caller or adjacent media helper missing: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
