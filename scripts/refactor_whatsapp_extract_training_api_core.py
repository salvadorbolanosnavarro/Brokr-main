#!/usr/bin/env python3
"""Extract WhatsApp training GET/PUT API while leaving the AI test endpoint in place."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_training_api import router as whatsapp_training_api_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_training_api_router)\n"
START = "class TrainingReq(BaseModel):\n"
END = "\n\nclass ProbarReq(BaseModel):\n"


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
            raise RuntimeError("training API end anchor not found")
        transformed = transformed[:i] + transformed[j:]
    elif "class TrainingReq" in transformed or "async def wa2_training_get" in transformed:
        raise RuntimeError("unexpected training API shape")

    for forbidden in (
        "class TrainingReq",
        "async def wa2_training_get",
        "async def wa2_training_put",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"training API remains in whatsapp.py: {forbidden}")

    # The AI sandbox remains with the brain until its service dependencies move.
    for required in (
        "class ProbarReq",
        "async def wa2_probar",
        "async def recepcion2_responde",
        "async def _buscar_inmuebles",
    ):
        if required not in transformed:
            raise RuntimeError(f"AI test/brain moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
