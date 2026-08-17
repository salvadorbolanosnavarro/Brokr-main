#!/usr/bin/env python3
"""Route only the best-effort reminder-sent PATCH through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        try:\n            async with httpx.AsyncClient(timeout=15) as c:\n                await c.patch(f"{SUPABASE_URL}/rest/v1/tareas",\n                              headers=_sb_headers({"Content-Type": "application/json"}),\n                              params={"id": f"eq.{t['id']}"}, json={"recordatorio_enviado": True})\n        except Exception as e:\n            _recordatorios_log.warning("No se pudo marcar recordatorio_enviado de %s: %s", t["id"], e)\n'''

NEW = '''        try:\n            await patch_rows(\n                "tareas",\n                {"id": f"eq.{t['id']}"},\n                {"recordatorio_enviado": True},\n                timeout=15,\n            )\n        except Exception as e:\n            _recordatorios_log.warning("No se pudo marcar recordatorio_enviado de %s: %s", t["id"], e)\n'''


def transform_source(source: str) -> str:
    marker = 'No se pudo marcar recordatorio_enviado de %s: %s'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one reminder-sent marker, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected reminder-sent patch state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
