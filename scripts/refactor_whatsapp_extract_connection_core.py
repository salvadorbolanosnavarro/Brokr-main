#!/usr/bin/env python3
"""Extract non-destructive WhatsApp number connection routes."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_connection import router as whatsapp_connection_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_connection_router)\n"
START = (
    "# =============================================================================\n"
    "# 1) CONEXIÓN DE NÚMEROS (Embedded Signup) — igual flujo de Meta, tabla propia\n"
    "# =============================================================================\n"
    "class ConnectReq(BaseModel):\n"
)
END = '@router.delete("/numeros/{numero_id}")\n'


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)
    if INCLUDE_LINE not in transformed:
        if ROUTER_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp router anchor not found")
        transformed = transformed.replace(ROUTER_ANCHOR, ROUTER_ANCHOR + INCLUDE_LINE, 1)

    if START in transformed:
        i = transformed.find(START)
        j = transformed.find(END, i)
        if j < 0:
            raise RuntimeError("number-delete boundary not found")
        transformed = transformed[:i] + transformed[j:]
    elif "class ConnectReq" in transformed or 'async def wa2_connect' in transformed:
        raise RuntimeError("unexpected connection-domain shape")

    for forbidden in (
        "class ConnectReq",
        "async def wa2_connect",
        "async def wa2_numero_verificar",
        "async def wa2_numeros_list",
        "class NumeroPatchReq",
        "async def wa2_numero_patch",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"connection route remains in whatsapp.py: {forbidden}")

    # Destructive deletion is deliberately outside this cut.
    if 'async def wa2_numero_delete' not in transformed:
        raise RuntimeError("destructive number delete moved unexpectedly")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
