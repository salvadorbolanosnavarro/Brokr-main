#!/usr/bin/env python3
"""Route only the Lead Ads contact-dedup GET through core.database.get_rows."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        async with httpx.AsyncClient(timeout=15) as client:\n            rx = await client.get(f"{SUPABASE_URL}/rest/v1/contactos",\n                                  headers=_sb_headers(), params=filtro)\n            existente = rx.json()[0] if (rx.status_code == 200 and rx.json()) else None\n'''

NEW = '''        async with httpx.AsyncClient(timeout=15) as client:\n            try:\n                filas_existentes = await get_rows(\n                    "contactos",\n                    filtro,\n                    timeout=15,\n                )\n            except httpx.HTTPStatusError:\n                filas_existentes = []\n            existente = filas_existentes[0] if filas_existentes else None\n'''


def transform_source(source: str) -> str:
    start = source.index("async def _fb_procesar_lead(valor: dict) -> None:")
    end = source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core Lead Ads contact lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
