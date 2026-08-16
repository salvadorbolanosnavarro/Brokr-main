#!/usr/bin/env python3
"""Route background photo-worker and pending-photo reads through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD_WORKER = '''                try:\n                    r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",\n                                         headers=sb_headers, params=params, timeout=30.0)\n                    if r.status_code != 200:\n                        break\n                    filas = r.json() or []\n                except Exception:\n                    break\n'''
NEW_WORKER = '''                try:\n                    filas = await get_rows("propiedades", params, timeout=30.0)\n                except Exception:\n                    break\n'''

OLD_PENDING = '''    pendientes = 0\n    try:\n        async with httpx.AsyncClient(timeout=30) as client:\n            r = await client.get(f"{SUPABASE_URL}/rest/v1/propiedades",\n                                 headers=sb_headers,\n                                 params={"org_id": f"eq.{org_id}", "select": "fotos"})\n            if r.status_code == 200:\n                for fila in (r.json() or []):\n                    fotos = fila.get("fotos") or []\n                    if isinstance(fotos, list) and any(_foto_migrable(f) for f in fotos):\n                        pendientes += 1\n    except Exception:\n        pass\n'''
NEW_PENDING = '''    pendientes = 0\n    try:\n        filas_pendientes = await get_rows(\n            "propiedades",\n            {"org_id": f"eq.{org_id}", "select": "fotos"},\n            timeout=30,\n        )\n        for fila in filas_pendientes:\n            fotos = fila.get("fotos") or []\n            if isinstance(fotos, list) and any(_foto_migrable(f) for f in fotos):\n                pendientes += 1\n    except Exception:\n        pass\n'''


def transform_source(source: str) -> str:
    start = source.index("async def _migrar_fotos_org(org_id: str):")
    end = source.index('\n\n@app.post("/easybroker/migrar-fotos")', start)
    block = source[start:end]
    if OLD_WORKER in block and NEW_WORKER not in block:
        block = block.replace(OLD_WORKER, NEW_WORKER, 1)
    elif not (OLD_WORKER not in block and NEW_WORKER in block):
        raise RuntimeError("Unexpected background photo-worker read state")
    if OLD_PENDING in block and NEW_PENDING not in block:
        block = block.replace(OLD_PENDING, NEW_PENDING, 1)
    elif not (OLD_PENDING not in block and NEW_PENDING in block):
        raise RuntimeError("Unexpected pending-photo read state")
    return source[:start] + block + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
