#!/usr/bin/env python3
"""Route only Facebook audience persistence through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=10) as client:\n            r = await client.post(\n                f"{SUPABASE_URL}/rest/v1/fb_audiences",\n                headers=_sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),\n                json={"user_id": user_id, "org_id": org_id, **datos})\n        if r.status_code not in (200, 201, 204):\n            if _fb_tabla_falta(r):\n                _fb_avisa_migracion("guardar público", r)\n            else:\n                _fb_log.error("No se pudo guardar el público: %s %s",\n                              r.status_code, (r.text or "")[:200])\n    except Exception as e:\n        _fb_log.error("Error guardando el público: %s", e)\n'''

NEW = '''    try:\n        try:\n            await post_rows(\n                "fb_audiences",\n                {"user_id": user_id, "org_id": org_id, **datos},\n                prefer="resolution=merge-duplicates,return=minimal",\n                timeout=10,\n                accepted_statuses=(200, 201, 204),\n            )\n        except httpx.HTTPStatusError as e:\n            if _fb_tabla_falta(e.response):\n                _fb_avisa_migracion("guardar público", e.response)\n            else:\n                _fb_log.error("No se pudo guardar el público: %s %s",\n                              e.response.status_code, (e.response.text or "")[:200])\n    except Exception as e:\n        _fb_log.error("Error guardando el público: %s", e)\n'''


def transform_source(source: str) -> str:
    marker = 'async def _fb_guardar_audiencia(user_id: str, org_id, datos: dict) -> None:'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one fb audience helper, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected fb audience POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
