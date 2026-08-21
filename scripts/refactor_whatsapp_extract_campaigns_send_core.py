#!/usr/bin/env python3
"""Extract WhatsApp campaign creation and execution from the root monolith."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_campaigns_send import router as whatsapp_campaigns_send_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_campaigns_send_router)\n"
REMOVE = {
    "CampanaCrearReq",
    "wa2_campana_crear",
    "_variables_para",
    "_correr_campana",
}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    found = set()
    for node in tree.body:
        name = getattr(node, "name", None)
        if name not in REMOVE:
            continue
        found.add(name)
        start = node.lineno - 1
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(d.lineno for d in decorators) - 1
        end = node.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
    missing = REMOVE - found
    if missing:
        raise RuntimeError(f"WhatsApp campaign-send nodes not found: {sorted(missing)}")
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    return "".join(lines)


def transform_source(source: str) -> str:
    transformed = source
    already_done = all(
        marker not in transformed
        for marker in (
            "class CampanaCrearReq",
            "async def wa2_campana_crear",
            "def _variables_para",
            "async def _correr_campana",
        )
    )
    if already_done and IMPORT_LINE in transformed and INCLUDE_LINE in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

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
        "class CampanaCrearReq",
        "async def wa2_campana_crear",
        "def _variables_para",
        "async def _correr_campana",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"campaign-send implementation remains: {forbidden}")
    if "whatsapp_campaigns_send_router" not in transformed:
        raise RuntimeError("campaign-send router mount missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
