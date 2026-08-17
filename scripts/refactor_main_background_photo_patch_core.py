#!/usr/bin/env python3
"""Route only the background photo-migration PATCH through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''                    try:\n                        await client.patch(\n                            f"{SUPABASE_URL}/rest/v1/propiedades",\n                            headers={**sb_headers, "Content-Type": "application/json",\n                                     "Prefer": "return=minimal"},\n                            params={"id": f"eq.{fila.get('id')}"},\n                            json={"fotos": nuevas}, timeout=30.0,\n                        )\n                        total_props += 1\n                        total_fotos += subidas\n                    except Exception:\n                        pass\n'''

NEW = '''                    try:\n                        try:\n                            await patch_rows(\n                                "propiedades",\n                                {"id": f"eq.{fila.get('id')}"},\n                                {"fotos": nuevas},\n                                timeout=30.0,\n                            )\n                        except httpx.HTTPStatusError:\n                            pass\n                        total_props += 1\n                        total_fotos += subidas\n                    except Exception:\n                        pass\n'''


def transform_source(source: str) -> str:
    marker = '[fotos] org {org_id}: {total_fotos} fotos guardadas en {total_props} propiedades'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one background-photo marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected background photo PATCH state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
