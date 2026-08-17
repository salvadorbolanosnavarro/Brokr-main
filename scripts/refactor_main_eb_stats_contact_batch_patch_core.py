#!/usr/bin/env python3
"""Route only EasyBroker stats existing-contact batch PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''            rp = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos",\n                headers={**sb_headers, "Prefer": "return=minimal"},\n                params={"id": f"in.({lista})"},\n                json={"es_potencial": True, "updated_at": ahora}\n            )\n            if rp.status_code in (200, 204):\n                marcados += len(lote)\n            else:\n                errores += len(lote)\n'''

NEW = '''            try:\n                await patch_rows(\n                    "contactos",\n                    {"id": f"in.({lista})"},\n                    {"es_potencial": True, "updated_at": ahora},\n                    timeout=60,\n                    accepted_statuses=(200, 204),\n                )\n                marcados += len(lote)\n            except httpx.HTTPStatusError:\n                errores += len(lote)\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/easybroker/import-stats")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one EasyBroker stats endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected EB stats contact batch PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
