#!/usr/bin/env python3
"""Route WhatsApp 2 Meta verification through fail-closed domain auth."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
IMPORT = "from routers.whatsapp_webhook_auth import meta_verify_response\n"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
BLOCK_START = '@router.get("/webhook")\ndef wa2_verify_webhook(request: Request):\n'
BLOCK_END = '@router.post("/webhook")\n'
REPLACEMENT = (
    '@router.get("/webhook")\n'
    'def wa2_verify_webhook(request: Request):\n'
    '    return meta_verify_response(request, WA2_VERIFY_TOKEN)\n\n\n'
)


def transform_source(source: str) -> str:
    transformed = source

    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp webhook auth import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    if BLOCK_START in transformed:
        start = transformed.index(BLOCK_START)
        end = transformed.find(BLOCK_END, start)
        if end == -1:
            raise RuntimeError("WhatsApp POST webhook anchor not found")
        transformed = transformed[:start] + REPLACEMENT + transformed[end:]
    elif "return meta_verify_response(request, WA2_VERIFY_TOKEN)" not in transformed:
        raise RuntimeError("Unknown WhatsApp verification state")

    if transformed.count('@router.get("/webhook")') != 1:
        raise RuntimeError("Unexpected GET webhook route count")
    if transformed.count('@router.post("/webhook")') != 1:
        raise RuntimeError("Unexpected POST webhook route count")
    if "return meta_verify_response(request, WA2_VERIFY_TOKEN)" not in transformed:
        raise RuntimeError("Fail-closed Meta challenge delegation missing")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    SOURCE.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
