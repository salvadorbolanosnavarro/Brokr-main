#!/usr/bin/env python3
"""Route AVM websearch page downloads through Core's SSRF-safe HTTP layer."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"
IMPORT = "from core.http import fetch_public_http_result\n"
IMPORT_ANCHOR = "from core.pdf_store import _pdf_store\n"
TARGET = "_try_httpx"
REPLACEMENT = '''    async def _try_httpx(url: str) -> Dict[str, Any]:
        async with sem_http:
            r = await fetch_public_http_result(
                url,
                timeout=FETCH_TIMEOUT,
                headers=headers,
            )
        ctype = (r.headers.get("content-type") or "").lower()
        if r.status_code >= 400 or "text/html" not in ctype:
            return {"ok": False, "status": r.status_code, "text": ""}
        return {"ok": True, "status": r.status_code, "text": _extract_visible_text(r.text)}
'''


def transform_source(source: str) -> str:
    tree = ast.parse(source)
    targets = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET
    ]
    if len(targets) > 1:
        raise RuntimeError("Multiple AVM _try_httpx helpers found")

    transformed = source
    if targets:
        node = targets[0]
        if node.end_lineno is None:
            raise RuntimeError("AVM _try_httpx has no end line")
        lines = source.splitlines(keepends=True)
        start = node.lineno - 1
        end = node.end_lineno
        original = "".join(lines[start:end])
        if "httpx.AsyncClient" not in original or "follow_redirects=True" not in original:
            raise RuntimeError("AVM _try_httpx no longer matches the unsafe legacy transport")
        lines[start:end] = [REPLACEMENT]
        transformed = "".join(lines)
    elif "await fetch_public_http_result(" not in transformed:
        raise RuntimeError("AVM _try_httpx helper not found")

    if IMPORT not in transformed:
        if IMPORT_ANCHOR not in transformed:
            raise RuntimeError("Core HTTP import anchor not found")
        transformed = transformed.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT, 1)

    parsed = ast.parse(transformed)
    remaining = [
        node for node in ast.walk(parsed)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == TARGET
    ]
    if len(remaining) != 1:
        raise RuntimeError("Expected exactly one hardened AVM _try_httpx helper")
    segment = ast.get_source_segment(transformed, remaining[0]) or ""
    if "fetch_public_http_result" not in segment:
        raise RuntimeError("AVM fetch still bypasses Core HTTP")
    if "follow_redirects=True" in segment or "httpx.AsyncClient" in segment:
        raise RuntimeError("Unsafe AVM direct fetch remains")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
