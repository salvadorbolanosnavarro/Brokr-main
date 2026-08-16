#!/usr/bin/env python3
"""Route only /contactos/importar-eb existing-contact read through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=15) as client:\n        r_existing = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos",\n            headers=sb_headers,\n            params={**filtro_existentes,\n                    "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"}\n        )\n    existing = r_existing.json() if r_existing.status_code == 200 else []\n'''

NEW = '''    try:\n        existing = await get_rows(\n            "contactos",\n            {**filtro_existentes,\n             "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas"},\n            timeout=15,\n        )\n    except httpx.HTTPStatusError:\n        existing = []\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/contactos/importar-eb")')
    end = source.index('\n\n@app.post("/contactos/importar-archivo")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core importar-eb existing-contact read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
