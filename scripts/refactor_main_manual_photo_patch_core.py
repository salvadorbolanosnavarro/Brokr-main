#!/usr/bin/env python3
"""Route only manual photo-migration property PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''            try:\n                rp = await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/propiedades",\n                    headers={**sb_headers, "Content-Type": "application/json",\n                             "Prefer": "return=minimal"},\n                    params={"id": f"eq.{pid}"},\n                    json={"fotos": nuevas},\n                )\n                if rp.status_code in (200, 204):\n                    propiedades_ok += 1\n                    fotos_subidas += subidas_prop\n                else:\n                    errores += 1\n            except Exception:\n                errores += 1\n'''

NEW = '''            try:\n                await patch_rows(\n                    "propiedades",\n                    {"id": f"eq.{pid}"},\n                    {"fotos": nuevas},\n                    timeout=60,\n                    accepted_statuses=(200, 204),\n                )\n                propiedades_ok += 1\n                fotos_subidas += subidas_prop\n            except Exception:\n                errores += 1\n'''


def transform_source(source: str) -> str:
    marker = '"propiedades_actualizadas": propiedades_ok'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one manual photo result marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected manual photo PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
