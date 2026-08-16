#!/usr/bin/env python3
"""Route only the Lead Ads anti-replay fb_leads_recibidos GET through Core."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # ── 0. ¿Ya lo procesamos? Meta reintenta y no queremos duplicados ──\n    try:\n        async with httpx.AsyncClient(timeout=10) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/fb_leads_recibidos",\n                headers=_sb_headers(),\n                params={"leadgen_id": f"eq.{leadgen_id}", "select": "id,procesado", "limit": "1"})\n        if r.status_code == 200 and r.json():\n            if (r.json()[0] or {}).get("procesado"):\n                _fb_log.info("Lead %s ya procesado; se ignora el reenvío.", leadgen_id)\n                return\n        elif _fb_tabla_falta(r):\n            _fb_avisa_migracion("procesar lead", r)\n    except Exception:\n        pass\n'''

NEW = '''    # ── 0. ¿Ya lo procesamos? Meta reintenta y no queremos duplicados ──\n    try:\n        try:\n            filas_previas = await get_rows(\n                "fb_leads_recibidos",\n                {"leadgen_id": f"eq.{leadgen_id}", "select": "id,procesado", "limit": "1"},\n                timeout=10,\n            )\n        except httpx.HTTPStatusError as e:\n            if _fb_tabla_falta(e.response):\n                _fb_avisa_migracion("procesar lead", e.response)\n            filas_previas = []\n        if filas_previas and (filas_previas[0] or {}).get("procesado"):\n            _fb_log.info("Lead %s ya procesado; se ignora el reenvío.", leadgen_id)\n            return\n    except Exception:\n        pass\n'''


def transform_source(source: str) -> str:
    start = source.index("async def _fb_procesar_lead(valor: dict) -> None:")
    end = source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core Lead Ads replay lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
