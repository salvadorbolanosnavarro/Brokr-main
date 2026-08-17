#!/usr/bin/env python3
"""Route only the EasyBroker bulk property upsert through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD_IMPORT = "from core.database import delete_rows, get_public_rows, get_rows, patch_rows, post_rows\n"
NEW_IMPORT = "from core.database import delete_rows, get_public_rows, get_rows, patch_rows, post_rows, upsert_rows\n"

OLD = '''    async with httpx.AsyncClient(timeout=60) as client:\n        for i in range(0, len(inmuebles_listos), UPSERT_BATCH):\n            chunk = inmuebles_listos[i:i+UPSERT_BATCH]\n            ultimo_fallo = "sin respuesta"\n            guardado = False\n            for intento in range(3):\n                try:\n                    ri = await client.post(\n                        f"{SUPABASE_URL}/rest/v1/propiedades",\n                        headers={**sb_headers,\n                                 "Prefer": "resolution=merge-duplicates,return=minimal"},\n                        params={"on_conflict": "org_id,eb_public_id"},\n                        json=chunk\n                    )\n                    if ri.status_code in (200, 201, 204):\n                        upserted += len(chunk)\n                        guardado = True\n                        break\n                    ultimo_fallo = f"Supabase {ri.status_code}: {ri.text[:200]}"\n                except Exception as e:\n                    ultimo_fallo = str(e)[:200]\n                await asyncio.sleep(1.5 * (2 ** intento))\n            if not guardado:\n                errores.append({\n                    "id": f"lote_{i // UPSERT_BATCH}",\n                    "error": ultimo_fallo\n                })\n'''

NEW = '''    async with httpx.AsyncClient(timeout=60) as client:\n        for i in range(0, len(inmuebles_listos), UPSERT_BATCH):\n            chunk = inmuebles_listos[i:i+UPSERT_BATCH]\n            ultimo_fallo = "sin respuesta"\n            guardado = False\n            for intento in range(3):\n                try:\n                    await upsert_rows(\n                        "propiedades",\n                        chunk,\n                        conflict="org_id,eb_public_id",\n                        prefer="resolution=merge-duplicates,return=minimal",\n                        timeout=60,\n                        accepted_statuses=(200, 201, 204),\n                    )\n                    upserted += len(chunk)\n                    guardado = True\n                    break\n                except httpx.HTTPStatusError as e:\n                    ultimo_fallo = f"Supabase {e.response.status_code}: {e.response.text[:200]}"\n                except Exception as e:\n                    ultimo_fallo = str(e)[:200]\n                await asyncio.sleep(1.5 * (2 ** intento))\n            if not guardado:\n                errores.append({\n                    "id": f"lote_{i // UPSERT_BATCH}",\n                    "error": ultimo_fallo\n                })\n'''


def transform_source(source: str) -> str:
    old_import_count = source.count(OLD_IMPORT)
    new_import_count = source.count(NEW_IMPORT)
    old_count = source.count(OLD)
    new_count = source.count(NEW)

    if old_import_count == 1 and new_import_count == 0 and old_count == 1 and new_count == 0:
        transformed = source.replace(OLD_IMPORT, NEW_IMPORT, 1).replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed

    if old_import_count == 0 and new_import_count == 1 and old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source

    raise RuntimeError(
        "Unexpected property bulk upsert state: "
        f"old_import={old_import_count}, new_import={new_import_count}, "
        f"old={old_count}, new={new_count}"
    )


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
