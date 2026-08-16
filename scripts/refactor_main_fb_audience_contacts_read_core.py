#!/usr/bin/env python3
"""Route the CRM contact read in /facebook/audiences/from-contacts through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=30) as client:\n        rc = await client.get(f"{SUPABASE_URL}/rest/v1/contactos",\n                              headers=_sb_headers(), params=filtros)\n    if rc.status_code != 200:\n        raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")\n    contactos = rc.json() or []\n'''

NEW = '''    try:\n        contactos = await get_rows(\n            "contactos",\n            filtros,\n            timeout=30,\n        )\n    except httpx.HTTPStatusError:\n        raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/facebook/audiences/from-contacts")')
    end = source.index('\n\nclass FbLookalikeRequest', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core audience contacts read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
