#!/usr/bin/env python3
"""Route only machote creation PostgREST POST through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        rd = await client.post(\n            f"{SUPABASE_URL}/rest/v1/machotes_contrato",\n            headers=_sb_headers({"Content-Type": "application/json",\n                                 "Prefer": "return=representation"}),\n            json=fila,\n        )\n        if rd.status_code not in (200, 201):\n            for p in (storage_path, storage_path_original):\n                if not p:\n                    continue\n                try:\n                    await client.delete(\n                        f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{p}",\n                        headers=_sb_headers())\n                except Exception:\n                    pass\n            raise HTTPException(status_code=500, detail=f"No se pudo guardar tu machote: {rd.text[:200]}")\n'''

NEW = '''        try:\n            await post_rows(\n                "machotes_contrato",\n                fila,\n                prefer="return=representation",\n                timeout=60,\n                accepted_statuses=(200, 201),\n            )\n        except httpx.HTTPStatusError as e:\n            for p in (storage_path, storage_path_original):\n                if not p:\n                    continue\n                try:\n                    await client.delete(\n                        f"{SUPABASE_URL}/storage/v1/object/{MACHOTES_BUCKET}/{p}",\n                        headers=_sb_headers())\n                except Exception:\n                    pass\n            raise HTTPException(status_code=500, detail=f"No se pudo guardar tu machote: {e.response.text[:200]}")\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/contrato/machote/crear")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one machote create endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected machote create POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
