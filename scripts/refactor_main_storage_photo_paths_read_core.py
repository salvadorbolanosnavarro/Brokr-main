#!/usr/bin/env python3
"""Route only _storage_rutas_fotos_de_usuario property read through Core."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=30) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/propiedades",\n                headers={\n                    "apikey": SUPABASE_SERVICE_KEY,\n                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                },\n                params={"user_id": f"eq.{user_id}", "select": "fotos", "limit": "10000"},\n            )\n            filas = r.json() if r.status_code == 200 else []\n            for fila in filas:\n                for url in (fila.get("fotos") or []):\n                    if not isinstance(url, str) or not url.startswith(prefijo_pub):\n                        continue\n                    resto = url[len(prefijo_pub):]\n                    if "/" not in resto:\n                        continue\n                    bucket, ruta = resto.split("/", 1)\n                    rutas.setdefault(bucket, set()).add(ruta)\n'''

NEW = '''    try:\n        try:\n            filas = await get_rows(\n                "propiedades",\n                {"user_id": f"eq.{user_id}", "select": "fotos", "limit": "10000"},\n                timeout=30,\n            )\n        except httpx.HTTPStatusError:\n            filas = []\n        for fila in filas:\n            for url in (fila.get("fotos") or []):\n                if not isinstance(url, str) or not url.startswith(prefijo_pub):\n                    continue\n                resto = url[len(prefijo_pub):]\n                if "/" not in resto:\n                    continue\n                bucket, ruta = resto.split("/", 1)\n                rutas.setdefault(bucket, set()).add(ruta)\n'''

def transform_source(source: str) -> str:
    start = source.index('async def _storage_rutas_fotos_de_usuario')
    end = source.index('\n\nasync def _storage_borrar_carpeta_usuario', start)
    block = source[start:end]
    if OLD in block and NEW not in block:
        block = block.replace(OLD, NEW, 1)
    elif not (OLD not in block and NEW in block):
        raise RuntimeError("Unexpected storage photo-path read state")
    return source[:start] + block + source[end:]

def main():
    source = MAIN.read_text(encoding="utf-8")
    out = transform_source(source)
    compile(out, str(MAIN), "exec")
    MAIN.write_text(out, encoding="utf-8")

if __name__ == "__main__":
    main()
