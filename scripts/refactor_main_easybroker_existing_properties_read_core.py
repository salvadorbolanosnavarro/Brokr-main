#!/usr/bin/env python3
"""Route only /easybroker/import-all existing-properties read through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # ─── Paso 1: leer filas existentes del usuario (para preservar notas/estatus) ───\n    existentes_por_eb_id = {}  # eb_public_id → {notas, estatus}\n    try:\n        async with httpx.AsyncClient(timeout=15) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades",\n                headers=sb_headers,\n                params={"user_id": f"eq.{user_id}",\n                        "eb_public_id": "not.is.null",\n                        "select": "eb_public_id,notas,estatus"}\n            )\n            if r.status_code == 200:\n                for row in r.json():\n                    eb_id = row.get("eb_public_id")\n                    if eb_id:\n                        existentes_por_eb_id[eb_id] = {\n                            "notas":   row.get("notas"),\n                            "estatus": row.get("estatus"),\n                        }\n    except Exception as e:\n        print(f"[import-all] Error leyendo existentes: {e}")\n'''

NEW = '''    # ─── Paso 1: leer filas existentes del usuario (para preservar notas/estatus) ───\n    existentes_por_eb_id = {}  # eb_public_id → {notas, estatus}\n    try:\n        try:\n            filas_existentes = await get_rows(\n                "propiedades",\n                {"user_id": f"eq.{user_id}",\n                 "eb_public_id": "not.is.null",\n                 "select": "eb_public_id,notas,estatus"},\n                timeout=15,\n            )\n        except httpx.HTTPStatusError:\n            filas_existentes = []\n        for row in filas_existentes:\n            eb_id = row.get("eb_public_id")\n            if eb_id:\n                existentes_por_eb_id[eb_id] = {\n                    "notas":   row.get("notas"),\n                    "estatus": row.get("estatus"),\n                }\n    except Exception as e:\n        print(f"[import-all] Error leyendo existentes: {e}")\n'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/easybroker/import-all")')
    end = source.index('\n\n@app.post("/contactos/importar-eb")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core EasyBroker existing-properties read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
