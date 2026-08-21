#!/usr/bin/env python3
"""Extract WhatsApp statistics I/O and endpoint from root."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

IMPORT_ANCHOR = "from core.storage import delete_objects, upload_object\n"
IMPORT_LINE = "from routers.whatsapp_stats_api import router as whatsapp_stats_api_router\n"
ROUTER_ANCHOR = 'router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])\n'
INCLUDE_LINE = "router.include_router(whatsapp_stats_api_router)\n"
REMOVE = {"_sb_diag", "_sb_get_paginado", "wa2_estadisticas"}


def _remove_nodes(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    ranges = []
    for node in tree.body:
        if getattr(node, "name", None) not in REMOVE:
            continue
        start = node.lineno - 1
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(d.lineno for d in decorators) - 1
        end = node.end_lineno
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        ranges.append((start, end))
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
        "async def _sb_diag",
        "async def _sb_get_paginado",
        "async def wa2_estadisticas",
        '@router.get("/estadisticas")',
    ):
        if forbidden in transformed:
            raise RuntimeError(f"statistics API implementation remains: {forbidden}")

    # Pure aggregation may already be extracted by the previous queue step.
    if "whatsapp_stats_api_router" not in transformed:
        raise RuntimeError("statistics API router mount missing")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
