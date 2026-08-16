#!/usr/bin/env python3
"""Route only /facebook/reconcile entity-ledger read through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=15) as client:\n        r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}",\n            headers=_sb_headers(),\n            params={"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"},\n        )\n    if _fb_tabla_falta(r):\n        _fb_avisa_migracion("reconciliar", r)\n        raise HTTPException(\n            status_code=503,\n            detail="Falta correr migracion-facebook-ads.sql en Supabase. Sin esa tabla "\n                   "Broquer no lleva registro de lo que creó y no puede reconciliar.")\n    if r.status_code != 200:\n        raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")\n\n    filas = r.json() or []\n'''

NEW = '''    try:\n        filas = await get_rows(\n            _FB_TABLA_ENTIDADES,\n            {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"},\n            timeout=15,\n        )\n    except httpx.HTTPStatusError as e:\n        if _fb_tabla_falta(e.response):\n            _fb_avisa_migracion("reconciliar", e.response)\n            raise HTTPException(\n                status_code=503,\n                detail="Falta correr migracion-facebook-ads.sql en Supabase. Sin esa tabla "\n                       "Broquer no lleva registro de lo que creó y no puede reconciliar.")\n        raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/facebook/reconcile")')
    end = source.index('\n\n@app.get("/facebook/page-posts")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core Facebook reconcile read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
