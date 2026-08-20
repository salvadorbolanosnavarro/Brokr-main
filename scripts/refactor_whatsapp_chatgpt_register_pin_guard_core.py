#!/usr/bin/env python3
"""Make WhatsApp ChatGPT registration fail closed when WA_REGISTER_PIN is absent."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "routers" / "whatsapp_chatgpt.py"
ANCHOR = (
    '    if not req.code.strip():\n'
    '        raise HTTPException(\n'
    '            status_code=400,\n'
    '            detail="Meta no devolvió código de autorización.",\n'
    '        )\n'
)
GUARD = (
    '    if req.register_number and not WA_REGISTER_PIN:\n'
    '        raise HTTPException(\n'
    '            status_code=500,\n'
    '            detail="WA_REGISTER_PIN no configurado.",\n'
    '        )\n'
)


def transform_source(source: str) -> str:
    transformed = source
    if GUARD not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("WhatsApp ChatGPT signup guard anchor not found")
        transformed = transformed.replace(ANCHOR, ANCHOR + GUARD, 1)
    if transformed.count("if req.register_number and not WA_REGISTER_PIN:") != 1:
        raise RuntimeError("Unexpected WhatsApp ChatGPT register-PIN guard count")
    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
