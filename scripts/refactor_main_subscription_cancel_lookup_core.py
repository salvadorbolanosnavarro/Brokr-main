#!/usr/bin/env python3
"""Route subscription_cancel's initial suscripciones read through Core only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # Obtener stripe_subscription_id de Supabase
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "select": "stripe_subscription_id,status", "order": "updated_at.desc", "limit": "1"}
        )
    row = r.json()[0] if r.status_code == 200 and r.json() else {}
'''

NEW = '''    # Obtener stripe_subscription_id de Supabase
    try:
        subscription_rows = await get_rows(
            "suscripciones",
            {"user_id": f"eq.{user_id}", "select": "stripe_subscription_id,status", "order": "updated_at.desc", "limit": "1"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        subscription_rows = []
    row = subscription_rows[0] if subscription_rows else {}
'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/subscription/cancel")')
    end = source.index('@app.post("/subscription/portal")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core subscription cancel lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
