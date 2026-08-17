#!/usr/bin/env python3
"""Route only the website-lead contact dedup GET through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        if telefono:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/contactos", headers=hdr,\n                params={"user_id": f"eq.{user_id}", "telefono": f"eq.{telefono}",\n                        "select": "id,notas,es_potencial", "limit": "1"})\n            filas = r.json() if r.status_code == 200 else []\n            existente = filas[0] if filas else None\n'''

NEW = '''        if telefono:\n            try:\n                filas = await get_rows(\n                    "contactos",\n                    {"user_id": f"eq.{user_id}", "telefono": f"eq.{telefono}",\n                     "select": "id,notas,es_potencial", "limit": "1"},\n                    timeout=10,\n                )\n            except httpx.HTTPStatusError:\n                filas = []\n            existente = filas[0] if filas else None\n'''


def transform_source(source: str) -> str:
    marker = "# 2) Dedup: si ya existe un contacto de este agente con el mismo"
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected exactly one website-lead dedup marker, found {source.count(marker)}")

    marker_at = source.index(marker)
    block_end = source.index("\n\n            if existente:", marker_at)
    block = source[marker_at:block_end]

    if OLD not in block:
        if NEW in block:
            return source
        raise RuntimeError("Unexpected website-lead contact dedup GET state")

    if block.count(OLD) != 1:
        raise RuntimeError("Expected exactly one direct contact dedup GET in target block")

    transformed_block = block.replace(OLD, NEW, 1)
    return source[:marker_at] + transformed_block + source[block_end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
