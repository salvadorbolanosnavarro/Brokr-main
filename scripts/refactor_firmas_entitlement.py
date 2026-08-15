#!/usr/bin/env python3
"""Apply the one-time fail-closed entitlement refactor to routers/firmas.py."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "routers" / "firmas.py"

IMPORT_ANCHOR = "from pydantic import BaseModel\n"
IMPORT_REPLACEMENT = (
    "from pydantic import BaseModel\n\n"
    "from core.subscriptions import require_paid_feature_access\n"
)
START_ANCHOR = "async def _suscripcion_activa(user_id: str) -> bool:\n"
END_ANCHOR = "\ndef _ip(request: Request) -> str:\n"

REPLACEMENT = '''async def _uid_max(request: Request) -> str:\n    """Require a trusted session and active Broquer Max entitlement."""\n    return await require_paid_feature_access(\n        request,\n        detail=(\n            "La firma electrónica es parte de Broquer Max. Suscríbete para "\n            "mandar documentos a firma."\n        ),\n    )\n\n'''


def transform(text: str) -> str:
    if "from core.subscriptions import require_paid_feature_access" in text:
        raise RuntimeError("Firmas entitlement refactor already appears applied")
    if text.count(IMPORT_ANCHOR) != 1:
        raise RuntimeError("expected one pydantic import anchor")
    if text.count(START_ANCHOR) != 1 or text.count(END_ANCHOR) != 1:
        raise RuntimeError("Firmas entitlement block does not match reviewed source")

    start = text.index(START_ANCHOR)
    end = text.index(END_ANCHOR, start)
    if "Falla ABIERTO" not in text[start:end]:
        raise RuntimeError("reviewed fail-open entitlement marker is missing")

    # Replace the reviewed function block before adding imports above it so
    # the recorded offsets cannot be shifted by earlier text insertion.
    text = text[:start] + REPLACEMENT + text[end + 1 :]
    text = text.replace(IMPORT_ANCHOR, IMPORT_REPLACEMENT, 1)
    return text


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    updated = transform(original)
    TARGET.write_text(updated, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(ROOT)} to fail-closed paid entitlement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
