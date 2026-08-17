#!/usr/bin/env python3
"""Route only the website-lead existing-contact PATCH through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''            await client.patch(\n                f"{SUPABASE_URL}/rest/v1/contactos", headers=hdr,\n                params={"id": f"eq.{existente['id']}"},\n                json={"es_potencial": True, "notas": nuevas_notas[:5000],\n                      "updated_at": ahora})\n'''

NEW = '''            try:\n                await patch_rows(\n                    "contactos",\n                    {"id": f"eq.{existente['id']}"},\n                    {"es_potencial": True, "notas": nuevas_notas[:5000],\n                     "updated_at": ahora},\n                    timeout=10,\n                )\n            except httpx.HTTPStatusError:\n                pass\n'''


def transform_source(source: str) -> str:
    marker = 'return {"ok": True, "duplicado": True}'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one website-lead duplicate marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected website-lead existing PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
