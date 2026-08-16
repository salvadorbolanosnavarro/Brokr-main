#!/usr/bin/env python3
"""Route _revisar_recordatorios's initial tareas read through core.database only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{SUPABASE_URL}/rest/v1/tareas", headers=_sb_headers(), params={
                "select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes",
                "completada": "eq.false", "recordatorio_enviado": "eq.false",
                "fecha_entrega": "not.is.null", "limit": "200",
            })
        if r.status_code >= 300:
            _recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", r.text[:200])
            return
        tareas = r.json()
    except Exception as e:
        _recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)
        return
'''

NEW = '''    try:
        try:
            tareas = await get_rows(
                "tareas",
                {
                    "select": "id,user_id,titulo,fecha_entrega,recordatorio_minutos_antes",
                    "completada": "eq.false", "recordatorio_enviado": "eq.false",
                    "fecha_entrega": "not.is.null", "limit": "200",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError as e:
            texto = e.response.text if e.response is not None else ""
            _recordatorios_log.warning("No se pudo leer tareas para recordatorios: %s", texto[:200])
            return
    except Exception as e:
        _recordatorios_log.error("Error consultando tareas para recordatorios: %s", e)
        return
'''


def transform_source(source: str) -> str:
    start = source.index("async def _revisar_recordatorios():")
    end = source.index("\n\nasync def _recordatorios_loop():", start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core reminder tareas read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
