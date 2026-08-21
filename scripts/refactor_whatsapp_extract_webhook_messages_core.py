#!/usr/bin/env python3
"""Replace inline WhatsApp webhook type/media parsing with the shared materializer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_webhook_messages import materializar_mensaje as _materializar_mensaje\n"
)
START = '                tipo_msg = msg.get("type")\n'
END = '                es_asesor = _es_asesor(numero, wa_id)\n'
REPLACEMENT = (
    '                tipo_msg, texto, media_bytes, media_mime, media_sufijo = await _materializar_mensaje(\n'
    '                    msg, numero\n'
    '                )\n\n'
)


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if "await _materializar_mensaje(" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("webhook message materializer start anchor not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("webhook advisor-identity anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    for forbidden in (
        'elif tipo_msg in ("audio", "voice"):',
        'elif tipo_msg == "image":',
        'elif tipo_msg == "document":',
        'elif tipo_msg == "video":',
    ):
        if forbidden in transformed[start : transformed.find(END, start) if END in transformed[start:] else start + 500]:
            raise RuntimeError(f"inline webhook media branch remains: {forbidden}")
    if "await _materializar_mensaje(" not in transformed:
        raise RuntimeError("webhook message materializer delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
