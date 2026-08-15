#!/usr/bin/env python3
"""Route get_user_rol's privileged usuarios read through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''async def get_user_rol(user_id: str) -> str:
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return "agente"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/usuarios",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"id": f"eq.{user_id}", "select": "rol", "limit": "1"}
            )
            if r.status_code == 200:
                rows = r.json()
                if rows:
                    return rows[0].get("rol") or "agente"
    except Exception:
        pass
    return "agente"
'''

NEW = '''async def get_user_rol(user_id: str) -> str:
    if not user_id or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return "agente"
    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol", "limit": "1"},
            timeout=8,
        )
        if rows:
            return rows[0].get("rol") or "agente"
    except Exception:
        pass
    return "agente"
'''


def transform_source(source: str) -> str:
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core get_user_rol block")
    return source.replace(OLD, NEW, 1)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
