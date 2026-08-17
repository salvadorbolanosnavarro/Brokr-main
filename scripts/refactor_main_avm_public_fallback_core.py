#!/usr/bin/env python3
"""Route only the AVM propiedades_avm fallback GET through public Core DB access."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD_IMPORT = "from core.database import delete_rows, get_rows, patch_rows, post_rows\n"
NEW_IMPORT = "from core.database import delete_rows, get_public_rows, get_rows, patch_rows, post_rows\n"

OLD = '''        # Fallback: buscar por ciudad sin PostGIS\n        async with httpx.AsyncClient(timeout=15) as client:\n            r2 = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades_avm",\n                headers=headers,\n                params={\n                    "ciudad": "eq.Morelia",\n                    "precio": "gt.0",\n                    "metros_construccion": "not.is.null",\n                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",\n                    "limit": req.max_resultados,\n                    "order": "precio.asc",\n                }\n            )\n        items = r2.json() if r2.status_code == 200 else []\n'''

NEW = '''        # Fallback: buscar por ciudad sin PostGIS\n        try:\n            items = await get_public_rows(\n                "propiedades_avm",\n                {\n                    "ciudad": "eq.Morelia",\n                    "precio": "gt.0",\n                    "metros_construccion": "not.is.null",\n                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",\n                    "limit": req.max_resultados,\n                    "order": "precio.asc",\n                },\n                timeout=15,\n            )\n        except httpx.HTTPStatusError:\n            items = []\n'''


def transform_source(source: str) -> str:
    marker = '# Fallback: buscar por ciudad sin PostGIS'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected exactly one AVM fallback marker, found {source.count(marker)}")

    old_count = source.count(OLD)
    new_count = source.count(NEW)
    old_import_count = source.count(OLD_IMPORT)
    new_import_count = source.count(NEW_IMPORT)

    if old_count == 1 and new_count == 0:
        if old_import_count != 1 or new_import_count != 0:
            raise RuntimeError(
                f"Unexpected core.database import state: old={old_import_count}, new={new_import_count}"
            )
        transformed = source.replace(OLD_IMPORT, NEW_IMPORT, 1).replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed

    if old_count == 0 and new_count == 1:
        if old_import_count != 0 or new_import_count != 1:
            raise RuntimeError(
                f"Unexpected migrated core.database import state: old={old_import_count}, new={new_import_count}"
            )
        compile(source, str(MAIN), "exec")
        return source

    raise RuntimeError(f"Unexpected AVM fallback state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
