#!/usr/bin/env python3
"""Route _fb_buscar_por_idempotencia through core.database.get_rows only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=10) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}",\n                headers=_sb_headers(),\n                params={"user_id": f"eq.{user_id}",\n                        "idempotency_key": f"eq.{idempotency_key}",\n                        "limit": "1"},\n            )\n        if r.status_code == 200 and r.json():\n            return r.json()[0]\n        if _fb_tabla_falta(r):\n            _fb_avisa_migracion("buscar idempotencia", r)\n    except Exception as e:\n        _fb_log.error("Error buscando idempotencia: %s", e)\n    return {}\n'''

NEW = '''    try:\n        try:\n            filas = await get_rows(\n                _FB_TABLA_ENTIDADES,\n                {"user_id": f"eq.{user_id}",\n                 "idempotency_key": f"eq.{idempotency_key}",\n                 "limit": "1"},\n                timeout=10,\n            )\n        except httpx.HTTPStatusError as e:\n            if _fb_tabla_falta(e.response):\n                _fb_avisa_migracion("buscar idempotencia", e.response)\n            return {}\n        if filas:\n            return filas[0]\n    except Exception as e:\n        _fb_log.error("Error buscando idempotencia: %s", e)\n    return {}\n'''


def transform_source(source: str) -> str:
    start = source.index("async def _fb_buscar_por_idempotencia(")
    end = source.index("\n\nasync def _fb_actualizar_entidad(", start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core FB idempotency lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
