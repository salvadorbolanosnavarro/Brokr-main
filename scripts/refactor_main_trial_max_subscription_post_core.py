#!/usr/bin/env python3
"""Route only trial-max subscription creation POST through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=10) as client:\n        r = await client.post(\n            f"{SUPABASE_URL}/rest/v1/suscripciones",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json=fila,\n        )\n        if r.status_code not in (200, 201):\n            raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")\n        # Quemar el regalo: aunque la fila se borre después, no se repite.\n'''

NEW = '''    try:\n        await post_rows(\n            "suscripciones",\n            fila,\n            prefer="return=minimal",\n            timeout=10,\n            accepted_statuses=(200, 201),\n        )\n    except httpx.HTTPStatusError:\n        raise HTTPException(status_code=502, detail="No se pudo activar la prueba. Intenta de nuevo.")\n    # Quemar el regalo: aunque la fila se borre después, no se repite.\n    async with httpx.AsyncClient(timeout=10) as client:\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/subscription/trial-max")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one trial-max endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected trial-max subscription POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
