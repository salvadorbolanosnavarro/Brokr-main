#!/usr/bin/env python3
"""Route only /contactos/importar-eb existing-contact PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                    filtro_patch = (f"org_id=eq.{org_id_import}" if org_id_import\n                                    else f"user_id=eq.{user_id}")\n                    rb = await client.patch(\n                        f"{SUPABASE_URL}/rest/v1/contactos?id=eq.{existente['id']}&{filtro_patch}",\n                        headers=sb_headers,\n                        json=patch\n                    )\n                    if rb.status_code in (200, 204):\n                        actualizados += 1\n                    else:\n                        errores += 1\n'''

NEW = '''                    filtro_patch = ({"org_id": f"eq.{org_id_import}"} if org_id_import\n                                    else {"user_id": f"eq.{user_id}"})\n                    try:\n                        await patch_rows(\n                            "contactos",\n                            {"id": f"eq.{existente['id']}", **filtro_patch},\n                            patch,\n                            timeout=20,\n                            accepted_statuses=(200, 204),\n                        )\n                        actualizados += 1\n                    except httpx.HTTPStatusError:\n                        errores += 1\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/contactos/importar-eb")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one importar-eb endpoint, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected EB existing-contact PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
