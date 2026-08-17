#!/usr/bin/env python3
"""Route only machote row deletion through core.database without touching Storage deletion."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        rd = await client.delete(\n            f"{SUPABASE_URL}/rest/v1/machotes_contrato",\n            headers=_sb_headers({"Prefer": "return=minimal"}),\n            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},\n        )\n    if rd.status_code not in (200, 204):\n        raise HTTPException(status_code=500, detail="No se pudo eliminar el machote.")\n'''

NEW = '''        try:\n            await delete_rows(\n                "machotes_contrato",\n                {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},\n                prefer="return=minimal",\n                timeout=15,\n                accepted_statuses=(200, 204),\n            )\n        except httpx.HTTPStatusError:\n            raise HTTPException(status_code=500, detail="No se pudo eliminar el machote.")\n'''


def transform_source(source: str) -> str:
    marker = '@app.delete("/contrato/machote/{machote_id}")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one machote delete endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected machote delete state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
