#!/usr/bin/env python3
"""Route subscription_status' suscripciones lookup through Core only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    _oid = await get_org_id_for_user(user_id)
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/suscripciones",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"}
        )
    if r.status_code != 200 or not r.json():
        return {"active": False, "plan": None, "status": "sin_suscripcion",
                "trial_disponible": await _trial_max_disponible(user_id)}

    row = r.json()[0]
'''

NEW = '''    _oid = await get_org_id_for_user(user_id)
    try:
        subscription_rows = await get_rows(
            "suscripciones",
            {"org_id": f"eq.{_oid}", "select": "*", "order": "updated_at.desc", "limit": "1"},
            timeout=8,
        )
    except httpx.HTTPStatusError:
        subscription_rows = []
    if not subscription_rows:
        return {"active": False, "plan": None, "status": "sin_suscripcion",
                "trial_disponible": await _trial_max_disponible(user_id)}

    row = subscription_rows[0]
'''


def transform_source(source: str) -> str:
    start = source.index('@app.get("/subscription/status")')
    end = source.index('# ════════════════════════════════════════════════════════════════\n# Trial de Broquer Max SIN tarjeta', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core subscription status lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
