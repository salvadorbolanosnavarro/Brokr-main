#!/usr/bin/env python3
"""Deterministically route _get_fb_meta's Supabase read through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''async def _get_fb_meta(user_id: str) -> dict:
    """Helper: recupera meta de Facebook del usuario desde Supabase."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_integrations",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            params={"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "meta", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta_raw = r.json()[0].get("meta", "{}")
'''

NEW = '''async def _get_fb_meta(user_id: str) -> dict:
    """Helper: recupera meta de Facebook del usuario desde Supabase."""
    try:
        rows = await get_rows(
            "user_integrations",
            {"user_id": f"eq.{user_id}", "provider": "eq.facebook", "select": "meta", "limit": "1"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    if not rows:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta_raw = rows[0].get("meta", "{}")
'''


def transform_source(source: str) -> str:
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core _get_fb_meta block")
    return source.replace(OLD, NEW, 1)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
