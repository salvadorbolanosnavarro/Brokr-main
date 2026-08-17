#!/usr/bin/env python3
"""Route only Facebook lead-log persistence through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        try:\n            async with httpx.AsyncClient(timeout=10) as client:\n                r = await client.post(\n                    f"{SUPABASE_URL}/rest/v1/fb_leads_recibidos",\n                    headers=_sb_headers({"Prefer": "return=minimal"}),\n                    json={**bitacora, **extra})\n            if r.status_code not in (200, 201, 204) and not _fb_tabla_falta(r):\n                if r.status_code != 409:\n                    _fb_log.error("No se pudo anotar el lead %s: %s %s",\n                                  leadgen_id, r.status_code, (r.text or "")[:200])\n        except Exception as e:\n            _fb_log.error("Error anotando el lead %s: %s", leadgen_id, e)\n'''

NEW = '''        try:\n            try:\n                await post_rows(\n                    "fb_leads_recibidos",\n                    {**bitacora, **extra},\n                    prefer="return=minimal",\n                    timeout=10,\n                    accepted_statuses=(200, 201, 204),\n                )\n            except httpx.HTTPStatusError as e:\n                if e.response.status_code != 409 and not _fb_tabla_falta(e.response):\n                    _fb_log.error("No se pudo anotar el lead %s: %s %s",\n                                  leadgen_id, e.response.status_code,\n                                  (e.response.text or "")[:200])\n        except Exception as e:\n            _fb_log.error("Error anotando el lead %s: %s", leadgen_id, e)\n'''


def transform_source(source: str) -> str:
    marker = 'async def _anota(extra: dict) -> None:'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one Facebook lead log helper, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected Facebook lead log POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
