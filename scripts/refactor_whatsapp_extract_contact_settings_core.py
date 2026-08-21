#!/usr/bin/env python3
"""Extract editable WhatsApp contact qualification/settings endpoint."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_contact_settings import router as whatsapp_contact_settings_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_contact_settings_router)\n"
START = '@router.patch("/contactos/{contacto_id}")\n'
END = (
    "\n\n# =============================================================================\n"
    "# 9.4) AUTOMATIZACIONES — recetas simples: disparador + pasos\n"
)


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
            raise RuntimeError("contact-settings end anchor not found")
        transformed = transformed[:i] + transformed[j:]
    elif "async def wa2_contacto_patch" in transformed:
        raise RuntimeError("unexpected contact-settings shape")

    if "async def wa2_contacto_patch" in transformed:
        raise RuntimeError("contact settings remain in whatsapp.py")
    if "async def wa2_agregar_nota" not in transformed:
        raise RuntimeError("contact-note endpoint moved unexpectedly")
    if "async def wa2_automatizaciones_list" not in transformed:
        raise RuntimeError("automation domain moved unexpectedly")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
