#!/usr/bin/env python3
"""Route subscription_activate's usuarios lookup through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # Buscar user_id por stripe_customer_id en tabla usuarios
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"stripe_customer_id": f"eq.{customer_id}", "select": "id,nombre,email"}
        )

    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")

    usuario = r.json()[0]
'''

NEW = '''    # Buscar user_id por stripe_customer_id en tabla usuarios
    try:
        usuarios = await get_rows(
            "usuarios",
            {"stripe_customer_id": f"eq.{customer_id}", "select": "id,nombre,email"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        usuarios = []

    if not usuarios:
        raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")

    usuario = usuarios[0]
'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/subscription/activate")')
    end = source.index('@app.get("/subscription/status")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core subscription activate lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
