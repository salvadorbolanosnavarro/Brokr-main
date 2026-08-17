#!/usr/bin/env python3
"""Route only CSV-import contact-property link POST through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                rv = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos_propiedades",\n                    headers={**sb_headers, "Prefer": "return=minimal"},\n                    json={"user_id": user_id, "contacto_id": contacto_id,\n                          "propiedad_id": propiedad_id, "relacion": "interes"}\n                )\n                if rv.status_code in (200, 201, 204):\n                    vinculos_nuevos += 1\n                    pares_existentes.add((contacto_id, propiedad_id))\n'''

NEW = '''                try:\n                    await post_rows(\n                        "contactos_propiedades",\n                        {"user_id": user_id, "contacto_id": contacto_id,\n                         "propiedad_id": propiedad_id, "relacion": "interes"},\n                        prefer="return=minimal",\n                        timeout=20,\n                        accepted_statuses=(200, 201, 204),\n                    )\n                    vinculos_nuevos += 1\n                    pares_existentes.add((contacto_id, propiedad_id))\n                except httpx.HTTPStatusError:\n                    pass\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/contactos/importar-archivo")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one CSV contact import endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected CSV contact-property link POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
