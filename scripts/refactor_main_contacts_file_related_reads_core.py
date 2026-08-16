#!/usr/bin/env python3
"""Route only the related property/link reads in /contactos/importar-archivo through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades",\n            headers=sb_headers,\n            params={**filtro_org, "eb_public_id": "not.is.null",\n                    "select": "id,eb_public_id", "limit": "5000"}\n        )\n        if r2.status_code == 200:\n            for row in r2.json():\n                if row.get("eb_public_id"):\n                    prop_por_eb_id[row["eb_public_id"]] = row["id"]\n        r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades",\n            headers=sb_headers,\n            params={"select": "contacto_id,propiedad_id", "limit": "20000"}\n        )\n        if r3.status_code == 200:\n            for v in r3.json():\n                pares_existentes.add((v.get("contacto_id"), v.get("propiedad_id")))\n'''

NEW = '''        try:\n            propiedades_existentes = await get_rows(\n                "propiedades",\n                {**filtro_org, "eb_public_id": "not.is.null",\n                 "select": "id,eb_public_id", "limit": "5000"},\n                timeout=20,\n            )\n        except httpx.HTTPStatusError:\n            propiedades_existentes = []\n        for row in propiedades_existentes:\n            if row.get("eb_public_id"):\n                prop_por_eb_id[row["eb_public_id"]] = row["id"]\n        try:\n            vinculos_existentes = await get_rows(\n                "contactos_propiedades",\n                {"select": "contacto_id,propiedad_id", "limit": "20000"},\n                timeout=20,\n            )\n        except httpx.HTTPStatusError:\n            vinculos_existentes = []\n        for v in vinculos_existentes:\n            pares_existentes.add((v.get("contacto_id"), v.get("propiedad_id")))\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/contactos/importar-archivo")')
    end = source.index('\n\n# ════════════════════════════════════════════════════════════════\n# Migración completa EasyBroker', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core related-read block")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
