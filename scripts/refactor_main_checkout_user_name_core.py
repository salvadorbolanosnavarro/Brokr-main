#!/usr/bin/env python3
"""Route subscription_checkout's usuarios nombre read through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=8) as client:
        r_nombre = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"id": f"eq.{user_id}", "select": "nombre"}
        )
    nombre = (r_nombre.json()[0] if r_nombre.status_code == 200 and r_nombre.json() else {}).get("nombre", email)
'''

NEW = '''    try:
        filas_nombre = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "nombre"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        filas_nombre = []
    nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)
'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/subscription/checkout")')
    end = source.index("# ════════════════════════════════════════════════════════════════\n# BROQUER PARA EMPRESAS", start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core checkout user-name read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
