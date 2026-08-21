#!/usr/bin/env python3
"""Extract read-only WhatsApp inbox endpoints."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_inbox_read import router as whatsapp_inbox_read_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_inbox_read_router)\n"
START = '@router.get("/conversaciones")\n'
END = "\n\nclass EnviarManualReq(BaseModel):\n"


def transform_source(source: str) -> str:
    transformed = source
    if IMPORT_LINE not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core Storage import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)
    if INCLUDE_LINE not in transformed:
        if ROUTER_ANCHOR not in transformed:
            raise RuntimeError("WhatsApp root router anchor not found")
        transformed = transformed.replace(ROUTER_ANCHOR, ROUTER_ANCHOR + INCLUDE_LINE, 1)

    if START in transformed:
        i = transformed.find(START)
        j = transformed.find(END, i)
        if j < 0:
            raise RuntimeError("inbox read end anchor not found")
        transformed = transformed[:i] + transformed[j:]
    elif "async def wa2_conversaciones_list" in transformed or "async def wa2_mensajes_list" in transformed:
        raise RuntimeError("unexpected inbox-read shape")

    for forbidden in ("async def wa2_conversaciones_list", "async def wa2_mensajes_list"):
        if forbidden in transformed:
            raise RuntimeError(f"read-only inbox handler remains: {forbidden}")

    for required in (
        "class EnviarManualReq",
        "async def wa2_enviar_manual",
        "async def wa2_lectura",
        "async def wa2_conversacion_patch",
    ):
        if required not in transformed:
            raise RuntimeError(f"inbox mutation moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
