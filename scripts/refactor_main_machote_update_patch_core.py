#!/usr/bin/env python3
"""Route only machote update PostgREST PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=15) as client:\n        r = await client.patch(\n            f"{SUPABASE_URL}/rest/v1/machotes_contrato",\n            headers=_sb_headers({"Content-Type": "application/json",\n                                 "Prefer": "return=representation"}),\n            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},\n            json=parche,\n        )\n    if r.status_code not in (200, 204) or not r.json():\n        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")\n    return r.json()[0]\n'''

NEW = '''    try:\n        rows = await patch_rows(\n            "machotes_contrato",\n            {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}"},\n            parche,\n            prefer="return=representation",\n            timeout=15,\n            accepted_statuses=(200, 204),\n        )\n    except httpx.HTTPStatusError:\n        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")\n    if not rows:\n        raise HTTPException(status_code=500, detail="No se pudieron guardar los cambios.")\n    return rows[0]\n'''


def transform_source(source: str) -> str:
    marker = '@app.patch("/contrato/machote/{machote_id}")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one machote update endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected machote update PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
