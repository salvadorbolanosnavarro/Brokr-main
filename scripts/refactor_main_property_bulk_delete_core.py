#!/usr/bin/env python3
"""Route only property bulk row DELETEs through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                rd = await client.delete(\n                    f"{SUPABASE_URL}/rest/v1/propiedades",\n                    headers={**sb_headers, "Prefer": "return=minimal"},\n                    params={**filtro, "id": f"in.({lista})"},\n                )\n                if rd.status_code in (200, 204):\n                    eliminadas += len(lote)\n'''

NEW = '''                try:\n                    await delete_rows(\n                        "propiedades",\n                        {**filtro, "id": f"in.({lista})"},\n                        prefer="return=minimal",\n                        timeout=60,\n                        accepted_statuses=(200, 204),\n                    )\n                    eliminadas += len(lote)\n                except httpx.HTTPStatusError:\n                    pass\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/propiedades/eliminar-masivo")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one property bulk delete endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected property bulk DELETE state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
