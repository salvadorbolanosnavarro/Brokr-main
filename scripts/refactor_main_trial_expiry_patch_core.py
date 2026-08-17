#!/usr/bin/env python3
"""Route only the best-effort trial-expiry PATCH through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=8) as client:\n            await client.patch(\n                f"{SUPABASE_URL}/rest/v1/suscripciones?id=eq.{sub_id}",\n                headers={\n                    "apikey": SUPABASE_SERVICE_KEY,\n                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                    "Content-Type": "application/json",\n                    "Prefer": "return=minimal",\n                },\n                json={"status": "expired", "updated_at": datetime.utcnow().isoformat()},\n            )\n    except Exception:\n        pass\n'''

NEW = '''    try:\n        await patch_rows(\n            "suscripciones",\n            {"id": f"eq.{sub_id}"},\n            {"status": "expired", "updated_at": datetime.utcnow().isoformat()},\n            timeout=8,\n        )\n    except Exception:\n        pass\n'''


def transform_source(source: str) -> str:
    marker = "async def _expirar_trial_suscripcion(sub_id) -> None:"
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one trial-expiry helper, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected trial-expiry patch state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
