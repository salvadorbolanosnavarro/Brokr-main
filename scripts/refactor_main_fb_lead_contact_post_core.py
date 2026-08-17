#!/usr/bin/env python3
"""Route only Facebook Lead Ads contact creation through core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''            rc = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos",\n                headers=_sb_headers({"Prefer": "return=minimal"}),\n                json={k: v for k, v in contacto.items() if v not in ("", None, [])})\n        if rc.status_code not in (200, 201, 204):\n            await _anota({"error_detail": f"No se pudo crear el contacto: {(rc.text or '')[:200]}"})\n            return\n'''

NEW = '''            try:\n                await post_rows(\n                    "contactos",\n                    {k: v for k, v in contacto.items() if v not in ("", None, [])},\n                    prefer="return=minimal",\n                    timeout=15,\n                    accepted_statuses=(200, 201, 204),\n                )\n            except httpx.HTTPStatusError as e:\n                await _anota({"error_detail": f"No se pudo crear el contacto: {(e.response.text or '')[:200]}"})\n                return\n'''


def transform_source(source: str) -> str:
    marker = 'Lead %s guardado como contacto %s del usuario %s'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one Facebook lead contact marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected Facebook lead contact POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
