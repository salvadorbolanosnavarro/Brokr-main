#!/usr/bin/env python3
"""Route only CSV-import new-contact POST through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                ri = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/contactos",\n                    headers={**sb_headers, "Prefer": "return=minimal"},\n                    json=nuevo\n                )\n                if ri.status_code in (200, 201, 204):\n                    importados += 1\n                    contacto_id = nuevo["id"]\n                    if tel:\n                        por_tel[tel] = {"id": contacto_id, **m}\n                    if email:\n                        por_email[email] = {"id": contacto_id, **m}\n                else:\n                    errores += 1\n                    continue\n'''

NEW = '''                try:\n                    await post_rows(\n                        "contactos",\n                        nuevo,\n                        prefer="return=minimal",\n                        timeout=20,\n                        accepted_statuses=(200, 201, 204),\n                    )\n                    importados += 1\n                    contacto_id = nuevo["id"]\n                    if tel:\n                        por_tel[tel] = {"id": contacto_id, **m}\n                    if email:\n                        por_email[email] = {"id": contacto_id, **m}\n                except httpx.HTTPStatusError:\n                    errores += 1\n                    continue\n'''


def transform_source(source: str) -> str:
    marker = 'nuevo["nombre"] = nombre or "Sin nombre"'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one CSV new-contact marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected CSV contact POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
