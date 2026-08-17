#!/usr/bin/env python3
"""Route only _fb_actualizar_entidad PATCH through Core."""
from pathlib import Path

# Harmless touch used only to trigger the temporary deterministic apply workflow.
ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD_IMPORT = 'from core.database import delete_rows, get_rows, post_rows\n'
NEW_IMPORT = 'from core.database import delete_rows, get_rows, patch_rows, post_rows\n'

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=10) as client:\n            r = await client.patch(\n                f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}",\n                headers=_sb_headers({"Prefer": "return=minimal"}),\n                params={"id": f"eq.{row_id}"},\n                json={**updates, "updated_at": datetime.now(timezone.utc).isoformat()},\n            )\n        if r.status_code not in (200, 204):\n            if _fb_tabla_falta(r):\n                _fb_avisa_migracion("actualizar entidad", r)\n            else:\n                _fb_log.error("No se pudo actualizar %s: %s %s",\n                              _FB_TABLA_ENTIDADES, r.status_code, (r.text or "")[:300])\n    except Exception as e:\n        _fb_log.error("Error actualizando %s: %s", _FB_TABLA_ENTIDADES, e)\n'''

NEW = '''    try:\n        try:\n            await patch_rows(\n                _FB_TABLA_ENTIDADES,\n                {"id": f"eq.{row_id}"},\n                {**updates, "updated_at": datetime.now(timezone.utc).isoformat()},\n                timeout=10,\n            )\n        except httpx.HTTPStatusError as e:\n            if _fb_tabla_falta(e.response):\n                _fb_avisa_migracion("actualizar entidad", e.response)\n            else:\n                _fb_log.error("No se pudo actualizar %s: %s %s",\n                              _FB_TABLA_ENTIDADES, e.response.status_code,\n                              (e.response.text or "")[:300])\n    except Exception as e:\n        _fb_log.error("Error actualizando %s: %s", _FB_TABLA_ENTIDADES, e)\n'''

def transform_source(source: str) -> str:
    if OLD_IMPORT in source and NEW_IMPORT not in source:
        source = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
    elif NEW_IMPORT not in source:
        raise RuntimeError("Unexpected core.database import state")

    start = source.index('async def _fb_actualizar_entidad')
    end = source.index('\n\n# ─── FACEBOOK OAUTH', start)
    block = source[start:end]
    if OLD in block and NEW not in block:
        block = block.replace(OLD, NEW, 1)
    elif not (OLD not in block and NEW in block):
        raise RuntimeError("Unexpected Facebook entity patch state")
    return source[:start] + block + source[end:]

def main():
    source = MAIN.read_text(encoding="utf-8")
    out = transform_source(source)
    compile(out, str(MAIN), "exec")
    MAIN.write_text(out, encoding="utf-8")

if __name__ == "__main__":
    main()
