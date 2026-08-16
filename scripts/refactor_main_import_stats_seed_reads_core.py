#!/usr/bin/env python3
"""Route EasyBroker import-stats seed reads through Core without touching writes."""
from pathlib import Path

# Harmless touch used only to trigger the temporary deterministic apply workflow.
ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # ─── Paso 1: propiedades ya importadas (eb_public_id → id interno) ───\n    prop_por_eb_id = {}\n    async with httpx.AsyncClient(timeout=20) as client:\n        r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/propiedades",\n            headers=sb_headers,\n            params={**filtro_org, "eb_public_id": "not.is.null",\n                    "select": "id,eb_public_id", "limit": "5000"}\n        )\n        if r.status_code == 200:\n            for row in r.json():\n                if row.get("eb_public_id"):\n                    prop_por_eb_id[row["eb_public_id"]] = row["id"]\n\n        # ─── Paso 2: contactos existentes (dedupe por teléfono/email) ───\n        r2 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos",\n            headers=sb_headers,\n            params={**filtro_org, "select": "id,telefono,email,es_potencial",\n                    "limit": "10000"}\n        )\n        existentes = r2.json() if r2.status_code == 200 else []\n\n        # ─── Paso 3: vínculos existentes (para no duplicar 'interes') ───\n        r3 = await client.get(\n            f"{SUPABASE_URL}/rest/v1/contactos_propiedades",\n            headers=sb_headers,\n            params={"select": "contacto_id,propiedad_id",\n                    "relacion": "eq.interes", "limit": "20000"}\n        )\n        pares_existentes = set()\n        if r3.status_code == 200:\n            for v in r3.json():\n                pares_existentes.add((v.get("contacto_id"), v.get("propiedad_id")))\n'''

NEW = '''    # ─── Paso 1: propiedades ya importadas (eb_public_id → id interno) ───\n    prop_por_eb_id = {}\n    try:\n        propiedades_importadas = await get_rows(\n            "propiedades",\n            {**filtro_org, "eb_public_id": "not.is.null",\n             "select": "id,eb_public_id", "limit": "5000"},\n            timeout=20,\n        )\n    except httpx.HTTPStatusError:\n        propiedades_importadas = []\n    for row in propiedades_importadas:\n        if row.get("eb_public_id"):\n            prop_por_eb_id[row["eb_public_id"]] = row["id"]\n\n    # ─── Paso 2: contactos existentes (dedupe por teléfono/email) ───\n    try:\n        existentes = await get_rows(\n            "contactos",\n            {**filtro_org, "select": "id,telefono,email,es_potencial",\n             "limit": "10000"},\n            timeout=20,\n        )\n    except httpx.HTTPStatusError:\n        existentes = []\n\n    # ─── Paso 3: vínculos existentes (para no duplicar 'interes') ───\n    try:\n        vinculos_existentes = await get_rows(\n            "contactos_propiedades",\n            {"select": "contacto_id,propiedad_id",\n             "relacion": "eq.interes", "limit": "20000"},\n            timeout=20,\n        )\n    except httpx.HTTPStatusError:\n        vinculos_existentes = []\n    pares_existentes = {\n        (v.get("contacto_id"), v.get("propiedad_id")) for v in vinculos_existentes\n    }\n'''

def transform_source(source: str) -> str:
    start = source.index('@app.post("/easybroker/import-stats")')
    end = source.index('\n\n@app.', start + 1)
    block = source[start:end]
    if OLD in block and NEW not in block:
        block = block.replace(OLD, NEW, 1)
    elif not (OLD not in block and NEW in block):
        raise RuntimeError("Unexpected import-stats seed-read state")
    return source[:start] + block + source[end:]

def main():
    source = MAIN.read_text(encoding="utf-8")
    out = transform_source(source)
    compile(out, str(MAIN), "exec")
    MAIN.write_text(out, encoding="utf-8")

if __name__ == "__main__":
    main()
