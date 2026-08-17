#!/usr/bin/env python3
"""Route only website-lead creation POST through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        r = await client.post(f"{SUPABASE_URL}/rest/v1/contactos", headers=hdr, json=nuevo)\n        if r.status_code not in (200, 201):\n            raise HTTPException(status_code=502, detail="No se pudo registrar el lead")\n'''

NEW = '''        try:\n            await post_rows(\n                "contactos",\n                nuevo,\n                prefer="return=minimal",\n                timeout=10,\n                accepted_statuses=(200, 201),\n            )\n        except httpx.HTTPStatusError:\n            raise HTTPException(status_code=502, detail="No se pudo registrar el lead")\n'''


def transform_source(source: str) -> str:
    marker = 'raise HTTPException(status_code=502, detail="No se pudo registrar el lead")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one website-lead create marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected website-lead create POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
