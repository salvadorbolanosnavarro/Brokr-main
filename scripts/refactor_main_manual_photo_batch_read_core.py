#!/usr/bin/env python3
"""Route only /easybroker/migrar-fotos batch property read through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=30) as client:\n            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",\n                                 headers=sb_headers, params=params)\n        if r.status_code != 200:\n            raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")\n        filas = r.json() or []\n    except HTTPException:\n        raise\n    except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")\n'''

NEW = '''    try:\n        filas = await get_rows("propiedades", params, timeout=30)\n    except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el inventario.")\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/easybroker/migrar-fotos")')
    end = source.index('\n\n# ════════════════════════════════════════════════════════════════', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core manual photo-batch read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
