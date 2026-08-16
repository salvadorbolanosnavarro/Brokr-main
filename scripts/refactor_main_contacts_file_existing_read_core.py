#!/usr/bin/env python3
"""Route only the existing-contact read in /contactos/importar-archivo through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=20) as client:\n        r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos",\n            headers=sb_headers,\n            params={**filtro_org, "limit": "10000",\n                    "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"}\n        )\n        existentes = r.json() if r.status_code == 200 else []\n'''

NEW = '''    async with httpx.AsyncClient(timeout=20) as client:\n        try:\n            existentes = await get_rows(\n                "contactos",\n                {**filtro_org, "limit": "10000",\n                 "select": "id,telefono,email,nombre,empresa,notas,fuente,probabilidad,calle,mpio,cp,wa,etiquetas,estatus"},\n                timeout=20,\n            )\n        except httpx.HTTPStatusError:\n            existentes = []\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/contactos/importar-archivo")')
    end = source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core existing-contact file-import read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
