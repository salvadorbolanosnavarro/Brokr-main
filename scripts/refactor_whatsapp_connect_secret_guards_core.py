#!/usr/bin/env python3
"""Make WhatsApp 2 connection fail closed when operational secrets are absent."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "whatsapp.py"
ANCHOR = (
    '    if not META_APP_ID or not META_APP_SECRET:\n'
    '        raise HTTPException(status_code=500, detail="META_APP_ID o META_APP_SECRET no configurados")\n'
)
GUARDS = (
    '    if not WA2_VERIFY_TOKEN:\n'
    '        raise HTTPException(status_code=500, detail="WA2_VERIFY_TOKEN no configurado")\n'
    '    if not req.coexistence and not WA2_REGISTER_PIN:\n'
    '        raise HTTPException(status_code=500, detail="WA_REGISTER_PIN no configurado")\n'
)


def transform_source(source: str) -> str:
    transformed = source
    if GUARDS not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("WhatsApp connect config guard anchor not found")
        transformed = transformed.replace(ANCHOR, ANCHOR + GUARDS, 1)

    if transformed.count('if not WA2_VERIFY_TOKEN:') != 1:
        raise RuntimeError("Unexpected WA2 verify-token guard count")
    if transformed.count('if not req.coexistence and not WA2_REGISTER_PIN:') != 1:
        raise RuntimeError("Unexpected WA2 register-pin guard count")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
