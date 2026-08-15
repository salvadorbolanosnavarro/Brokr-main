#!/usr/bin/env python3
"""Route get_user_access_state's privileged usuarios read through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

NEW_TAIL = '''    try:
        rows = await get_rows(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "rol,activo", "limit": "1"},
            timeout=8,
        )
        if rows:
            return {
                "rol": rows[0].get("rol") or "agente",
                "activo": rows[0].get("activo") if rows[0].get("activo") is not None else True,
            }
    except Exception:
        pass
    return default
'''


def transform_source(source: str) -> str:
    start = source.index("async def get_user_access_state(user_id: str) -> dict:")
    end = source.index("# ─────────────────────────────────────────────\n# TELEMETRÍA", start)
    block = source[start:end]

    legacy_url = 'f"{SUPABASE_URL}/rest/v1/usuarios"'
    core_call = 'rows = await get_rows(\n            "usuarios",'
    legacy_count = block.count(legacy_url)
    core_count = block.count(core_call)
    if legacy_count == 0 and core_count == 1:
        return source
    if legacy_count != 1 or core_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core usuarios read in get_user_access_state")

    try_start = block.index("    try:\n")
    return_start = block.rindex("    return default")
    return_end = block.index("\n", return_start) + 1
    transformed_block = block[:try_start] + NEW_TAIL + block[return_end:]
    return source[:start] + transformed_block + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
