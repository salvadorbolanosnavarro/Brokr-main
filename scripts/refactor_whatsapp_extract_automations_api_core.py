#!/usr/bin/env python3
"""Extract WhatsApp automation CRUD while leaving the execution engine in root."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_automations_api import router as whatsapp_automations_api_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_automations_api_router)\n"
START = "class AutomatizacionReq(BaseModel):\n"
END = "async def _correr_automatizaciones(item: dict, numero: dict, user_id: str) -> bool:\n"


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
            raise RuntimeError("automation execution boundary not found")
        transformed = transformed[:i] + transformed[j:]
    elif "async def wa2_automatizaciones_list" in transformed or "async def wa2_automatizacion_crear" in transformed:
        raise RuntimeError("unexpected automation CRUD shape")

    for forbidden in (
        "class AutomatizacionReq",
        "def _limpiar_automatizacion",
        "async def wa2_automatizaciones_list",
        "async def wa2_automatizacion_crear",
        "async def wa2_automatizacion_patch",
        "async def wa2_automatizacion_delete",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"automation CRUD implementation remains: {forbidden}")

    for required in (
        "async def _correr_automatizaciones",
        "async def _flujo_ejecutar",
        "_AUTO_COOLDOWN_SEG = 120",
    ):
        if required not in transformed:
            raise RuntimeError(f"automation execution engine moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
