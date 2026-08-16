#!/usr/bin/env python3
"""Route admin_list_users' subscriptions read through Core only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # 2) Traer todas las suscripciones (más reciente primero)
    async with httpx.AsyncClient(timeout=15) as client:
        r_subs = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={
                "select": "user_id,plan_id,plan_nombre,status,updated_at",
                "order": "updated_at.desc",
                "limit": "10000",
            },
        )
    subs_by_user = {}
    if r_subs.status_code == 200:
        for s in r_subs.json():
            uid = s.get("user_id")
            if uid and uid not in subs_by_user:  # primera = más reciente
                subs_by_user[uid] = s
'''

NEW = '''    # 2) Traer todas las suscripciones (más reciente primero)
    try:
        subs = await get_rows(
            "suscripciones",
            {
                "select": "user_id,plan_id,plan_nombre,status,updated_at",
                "order": "updated_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError:
        subs = []
    subs_by_user = {}
    for s in subs:
        uid = s.get("user_id")
        if uid and uid not in subs_by_user:  # primera = más reciente
            subs_by_user[uid] = s
'''


def transform_source(source: str) -> str:
    start = source.index('@app.get("/admin/users")')
    end = source.index('class AdminRolReq(BaseModel):', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core admin subscriptions lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
