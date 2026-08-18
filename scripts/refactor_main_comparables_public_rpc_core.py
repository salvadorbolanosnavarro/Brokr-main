#!/usr/bin/env python3
"""Route only comparables PostGIS public RPC through core.database."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD_IMPORT = 'from core.database import delete_rows, get_public_rows, get_rows, patch_rows, post_rows, upsert_rows\n'
NEW_IMPORT = 'from core.database import call_public_rpc, delete_rows, get_public_rows, get_rows, patch_rows, post_rows, upsert_rows\n'

OLD_RPC = '''    headers = {\n        "apikey": SUPABASE_KEY,\n        "Authorization": f"Bearer {SUPABASE_KEY}",\n        "Content-Type": "application/json",\n    }\n\n    async with httpx.AsyncClient(timeout=15) as client:\n        r = await client.post(\n            f"{SUPABASE_URL}/rest/v1/rpc/buscar_cercanos",\n            headers=headers,\n            json=payload,\n        )\n\n    if r.status_code not in (200, 201):\n        # Fallback: buscar por ciudad sin PostGIS\n        try:\n            items = await get_public_rows(\n                "propiedades_avm",\n                {\n                    "ciudad": "eq.Morelia",\n                    "precio": "gt.0",\n                    "metros_construccion": "not.is.null",\n                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",\n                    "limit": req.max_resultados,\n                    "order": "precio.asc",\n                },\n                timeout=15,\n            )\n        except httpx.HTTPStatusError:\n            items = []\n    else:\n        items = r.json() or []\n'''

NEW_RPC = '''    try:\n        items = await call_public_rpc(\n            "buscar_cercanos",\n            payload,\n            timeout=15,\n            accepted_statuses=(200, 201),\n        ) or []\n    except httpx.HTTPStatusError:\n        # Fallback: buscar por ciudad sin PostGIS\n        try:\n            items = await get_public_rows(\n                "propiedades_avm",\n                {\n                    "ciudad": "eq.Morelia",\n                    "precio": "gt.0",\n                    "metros_construccion": "not.is.null",\n                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",\n                    "limit": req.max_resultados,\n                    "order": "precio.asc",\n                },\n                timeout=15,\n            )\n        except httpx.HTTPStatusError:\n            items = []\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/api/comparables-cercanos")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one comparables endpoint, found {source.count(marker)}")

    old_import = source.count(OLD_IMPORT)
    new_import = source.count(NEW_IMPORT)
    start = source.index(marker)
    end = source.index('\n\n# ', start)
    block = source[start:end]
    old_rpc = block.count(OLD_RPC)
    new_rpc = block.count(NEW_RPC)

    if old_import == 1 and new_import == 0 and old_rpc == 1 and new_rpc == 0:
        transformed = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
        start = transformed.index(marker)
        end = transformed.index('\n\n# ', start)
        block = transformed[start:end]
        transformed = transformed[:start] + block.replace(OLD_RPC, NEW_RPC, 1) + transformed[end:]
        compile(transformed, str(MAIN), "exec")
        return transformed

    if old_import == 0 and new_import == 1 and old_rpc == 0 and new_rpc == 1:
        compile(source, str(MAIN), "exec")
        return source

    raise RuntimeError(
        f"Unexpected comparables RPC state: imports old={old_import}, new={new_import}; rpc old={old_rpc}, new={new_rpc}"
    )


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == '__main__':
    main()
