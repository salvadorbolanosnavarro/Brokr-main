#!/usr/bin/env python3
"""Route only CSV-import existing-contact PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                if patch:\n                    patch["updated_at"] = now_iso\n                    rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos",\n                        headers={**sb_headers, "Prefer": "return=minimal"},\n                        params={"id": f"eq.{contacto_id}"},\n                        json=patch\n                    )\n                    if rb.status_code in (200, 204):\n                        actualizados += 1\n                        existente.update(patch)\n                    else:\n                        errores += 1\n                else:\n                    omitidos += 1\n'''

NEW = '''                if patch:\n                    patch["updated_at"] = now_iso\n                    try:\n                        await patch_rows(\n                            "contactos",\n                            {"id": f"eq.{contacto_id}"},\n                            patch,\n                            timeout=20,\n                            accepted_statuses=(200, 204),\n                        )\n                        actualizados += 1\n                        existente.update(patch)\n                    except httpx.HTTPStatusError:\n                        errores += 1\n                else:\n                    omitidos += 1\n'''


def transform_source(source: str) -> str:
    marker = 'existente.update(patch)'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one CSV contact update marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected CSV contact PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
