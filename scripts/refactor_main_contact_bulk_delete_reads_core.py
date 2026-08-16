#!/usr/bin/env python3
"""Route only contact bulk-delete verification reads through Core."""
from pathlib import Path

# Harmless touch used only to trigger the temporary deterministic apply workflow.
ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    filas: list = []\n    try:\n        async with httpx.AsyncClient(timeout=60) as client:\n            if todos:\n                r = await client.get(f"{SUPABASE_URL}/rest/v1/contactos",\n                                     headers=sb_headers,\n                                     params={**filtro, "select": "id", "limit": "10000"})\n                if r.status_code != 200:\n                    raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")\n                filas = r.json() or []\n            else:\n                for i in range(0, len(ids), 200):\n                    lote = ids[i:i+200]\n                    lista = ",".join(f'"{str(x)}"' for x in lote)\n                    r = await client.get(f"{SUPABASE_URL}/rest/v1/contactos",\n                                         headers=sb_headers,\n                                         params={**filtro, "select": "id",\n                                                 "id": f"in.({lista})"})\n                    if r.status_code != 200:\n                        raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")\n                    filas.extend(r.json() or [])\n    except HTTPException:\n        raise\n    except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")\n'''

NEW = '''    filas: list = []\n    try:\n        if todos:\n            filas = await get_rows(\n                "contactos",\n                {**filtro, "select": "id", "limit": "10000"},\n                timeout=60,\n            )\n        else:\n            for i in range(0, len(ids), 200):\n                lote = ids[i:i+200]\n                lista = ",".join(f'"{str(x)}"' for x in lote)\n                filas.extend(await get_rows(\n                    "contactos",\n                    {**filtro, "select": "id", "id": f"in.({lista})"},\n                    timeout=60,\n                ))\n    except Exception:\n        raise HTTPException(status_code=500, detail="No se pudo leer el directorio.")\n'''

def transform_source(source: str) -> str:
    start = source.index('@app.post("/contactos/eliminar-masivo")')
    end = source.index('\n\n@app.get("/propiedades")', start)
    block = source[start:end]
    if OLD in block and NEW not in block:
        block = block.replace(OLD, NEW, 1)
    elif not (OLD not in block and NEW in block):
        raise RuntimeError("Unexpected contact bulk-delete read state")
    return source[:start] + block + source[end:]

def main():
    source = MAIN.read_text(encoding="utf-8")
    out = transform_source(source)
    compile(out, str(MAIN), "exec")
    MAIN.write_text(out, encoding="utf-8")

if __name__ == "__main__":
    main()
