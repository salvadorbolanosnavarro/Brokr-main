#!/usr/bin/env python3
"""Deterministically route /profile/status integration reads through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # Una sola query trae AMBAS integraciones (EB + FB) del usuario
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_integrations",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                params={"user_id": f"eq.{user_id}",
                        "provider": "in.(easybroker,facebook)",
                        "select": "provider,api_key,meta"}
            )
            if r.status_code != 200:
                return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
            rows = r.json()
    except Exception:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
'''

NEW = '''    # Una sola query trae AMBAS integraciones (EB + FB) del usuario.
    # Core conserva el acceso privilegiado en un solo lugar; este endpoint
    # sigue siendo fail-soft ante cualquier rechazo o fallo de transporte.
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "user_id": f"eq.{user_id}",
                "provider": "in.(easybroker,facebook)",
                "select": "provider,api_key,meta",
            },
            timeout=8,
        )
    except Exception:
        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}
'''


def transform_source(source: str) -> str:
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f"Expected exactly one /profile/status legacy block, found {count}")
    return source.replace(OLD, NEW, 1)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
