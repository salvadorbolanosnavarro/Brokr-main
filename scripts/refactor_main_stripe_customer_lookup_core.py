#!/usr/bin/env python3
"""Route _get_or_create_stripe_customer's initial usuarios read through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # 1. Buscar en Supabase
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"id": f"eq.{user_id}", "select": "stripe_customer_id,nombre"}
        )
        row = r.json()[0] if r.status_code == 200 and r.json() else {}
'''

NEW = '''    # 1. Buscar en Supabase
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "stripe_customer_id,nombre"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        rows = []
    row = rows[0] if rows else {}
'''


def transform_source(source: str) -> str:
    start = source.index("async def _get_or_create_stripe_customer(user_id: str, email: str, nombre: str) -> str:")
    end = source.index('@app.post("/subscription/checkout")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core Stripe customer lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
