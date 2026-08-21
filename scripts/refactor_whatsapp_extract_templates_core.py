#!/usr/bin/env python3
"""Extract WhatsApp template listing/creation while leaving template sending in root."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_templates import router as whatsapp_templates_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_templates_router)\n"
START = "class PlantillaCrearReq(BaseModel):\n"
END = "class PlantillaEnviarReq(BaseModel):\n"


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
            raise RuntimeError("template-send boundary not found")
        transformed = transformed[:i] + transformed[j:]
    elif "async def wa2_plantillas_list" in transformed or "async def wa2_plantilla_crear" in transformed:
        raise RuntimeError("unexpected template-management shape")

    for forbidden in (
        "class PlantillaCrearReq",
        "async def wa2_plantillas_list",
        "async def wa2_plantilla_crear",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"template-management implementation remains: {forbidden}")

    for required in (
        "class PlantillaEnviarReq",
        "async def wa2_enviar_plantilla",
        '@router.post("/mensajes/plantilla")',
    ):
        if required not in transformed:
            raise RuntimeError(f"template sending moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
