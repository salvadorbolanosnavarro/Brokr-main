#!/usr/bin/env python3
"""Extract campaign read/audience endpoints while keeping send/create execution in root."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = (
    "from routers.whatsapp_campaigns_read import (\n"
    "    _audiencia_campana, _numero_visible, router as whatsapp_campaigns_read_router,\n"
    ")\n"
)
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_campaigns_read_router)\n"
REMOVE = {
    "CampanaAudienciaReq",
    "wa2_etiquetas_list",
    "wa2_campana_audiencia",
    "wa2_campanas_list",
    "wa2_campana_detalle",
}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    for node in tree.body:
        name = getattr(node, "name", None)
        if name not in REMOVE:
            continue
        start = node.lineno - 1
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(d.lineno for d in decorators) - 1
        end = node.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
    if not ranges and any(name in source for name in REMOVE):
        raise RuntimeError("campaign read nodes could not be located")
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


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

    transformed = _remove_nodes(transformed)

    for forbidden in (
        "class CampanaAudienciaReq",
        "async def wa2_etiquetas_list",
        "async def wa2_campana_audiencia",
        "async def wa2_campanas_list",
        "async def wa2_campana_detalle",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"campaign read implementation remains: {forbidden}")

    for required in (
        "class CampanaCrearReq",
        "async def wa2_campana_crear",
        "async def _correr_campana",
        "audiencia = await _audiencia_campana(numero, etiqueta)",
        "_, numero = await _numero_visible(request, req.numero_id)",
    ):
        if required not in transformed:
            raise RuntimeError(f"campaign send/create path moved unexpectedly: {required}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
