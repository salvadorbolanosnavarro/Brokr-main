#!/usr/bin/env python3
"""Extract the SSRF-hardened AVM websearch domain from main.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
START = "# ────────────────────────────────────────────\n# AVM — OPINIÓN DE VALOR CON INVESTIGACIÓN CONTROLADA DE COMPARABLES\n# ────────────────────────────────────────────\n"
END = "# ────────────────────────────────────────────\n# AVM — PDF DE OPINIÓN DE VALOR\n# ────────────────────────────────────────────\n"
MOUNT = '''# AVM con investigación controlada de comparables web.\nfrom routers.avm_websearch import router as avm_websearch_router\napp.include_router(avm_websearch_router)\n\n'''
ANCHOR = "# Comparables AVM vía Apify/Inmuebles24.\n"
HARDENED_MARKER = "await fetch_public_http_result("
UNSAFE_MARKER = "httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True, headers=headers)"


def transform_source(source: str) -> str:
    transformed = source

    if START in transformed:
        start = transformed.index(START)
        end = transformed.find(END, start)
        if end == -1:
            raise RuntimeError("AVM websearch block end marker not found")
        block = transformed[start:end]
        if HARDENED_MARKER not in block:
            if UNSAFE_MARKER in block:
                raise RuntimeError("AVM websearch must be SSRF-hardened before extraction")
            raise RuntimeError("AVM websearch hardened transport marker not found")
        transformed = transformed[:start] + transformed[end:]
    elif '@app.post("/api/avm-websearch")' in transformed or "class AvmWebSearchRequest" in transformed:
        raise RuntimeError("Partial AVM websearch extraction detected")

    if MOUNT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("AVM websearch router anchor not found")
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for needle in (
        '@app.post("/api/avm-websearch")',
        "async def avm_websearch(",
        "class AvmWebSearchRequest(BaseModel):",
        "async def _fetch_candidate_pages(",
        "async def _collect_search_candidates(",
        "async def _claude_extract_and_value(",
        "async def _firecrawl_scrape(",
    ):
        if needle in transformed:
            raise RuntimeError(f"AVM websearch implementation still present in main: {needle}")

    if '@app.post("/avm-pdf")' not in transformed:
        raise RuntimeError("AVM PDF route moved unexpectedly")
    compile(transformed, str(MAIN), "exec")
    return transformed


def main() -> None:
    MAIN.write_text(transform_source(MAIN.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
