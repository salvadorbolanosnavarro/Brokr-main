#!/usr/bin/env python3
"""Deterministically route /profile/status integration reads through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

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
    endpoint_start = source.index('@app.get("/profile/status")')
    endpoint_end = source.index("# ────────────────────────────────────────────\n# GROQ CHAT PROXY", endpoint_start)
    endpoint = source[endpoint_start:endpoint_end]

    legacy_url = 'f"{SUPABASE_URL}/rest/v1/user_integrations"'
    core_call = 'rows = await get_rows(\n            "user_integrations",'
    legacy_count = endpoint.count(legacy_url)
    core_count = endpoint.count(core_call)

    if legacy_count == 0 and core_count == 1:
        return source
    if legacy_count != 1 or core_count != 0:
        raise RuntimeError(
            "Expected exactly one legacy or one Core user_integrations read in /profile/status"
        )

    block_start = source.index("    # Una sola query trae AMBAS integraciones (EB + FB) del usuario", endpoint_start, endpoint_end)
    block_end = source.index("    # Parsear cada provider", block_start, endpoint_end)
    return source[:block_start] + NEW + source[block_end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
