#!/usr/bin/env python3
"""Route only _fb_reservar_creacion POST through core.database."""
# Temporary apply-workflow trigger; remove with the transform after application.
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:\n        async with httpx.AsyncClient(timeout=10) as client:\n            r = await client.post(\n                f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}",\n                headers=_sb_headers({"Prefer": "return=representation"}),\n                json=fila,\n            )\n        if r.status_code in (200, 201):\n            filas = r.json() if r.text else []\n            return {"modo": "nuevo", "row_id": (filas[0]["id"] if filas else fila["id"])}\n\n        if _fb_tabla_falta(r):\n            _fb_avisa_migracion("reservar creación", r)\n            return {"modo": "sin_tabla"}\n\n        # 409 = chocó con el índice único → ya hay una creación con esa llave.\n        if r.status_code == 409 and idempotency_key:\n            previa = await _fb_buscar_por_idempotencia(user_id, idempotency_key)\n            if previa:\n                return {"modo": "duplicado", "row": previa}\n\n        _fb_log.error("No se pudo registrar la creación en %s: %s %s",\n                      _FB_TABLA_ENTIDADES, r.status_code, (r.text or "")[:300])\n    except Exception as e:\n        _fb_log.error("Error registrando la creación en %s: %s", _FB_TABLA_ENTIDADES, e)\n'''

NEW = '''    try:\n        try:\n            filas = await post_rows(\n                _FB_TABLA_ENTIDADES,\n                fila,\n                prefer="return=representation",\n                timeout=10,\n                accepted_statuses=(200, 201),\n            )\n            return {"modo": "nuevo", "row_id": (filas[0]["id"] if filas else fila["id"])}\n        except httpx.HTTPStatusError as e:\n            r = e.response\n            if _fb_tabla_falta(r):\n                _fb_avisa_migracion("reservar creación", r)\n                return {"modo": "sin_tabla"}\n\n            # 409 = chocó con el índice único → ya hay una creación con esa llave.\n            if r.status_code == 409 and idempotency_key:\n                previa = await _fb_buscar_por_idempotencia(user_id, idempotency_key)\n                if previa:\n                    return {"modo": "duplicado", "row": previa}\n\n            _fb_log.error("No se pudo registrar la creación en %s: %s %s",\n                          _FB_TABLA_ENTIDADES, r.status_code, (r.text or "")[:300])\n    except Exception as e:\n        _fb_log.error("Error registrando la creación en %s: %s", _FB_TABLA_ENTIDADES, e)\n'''


def transform_source(source: str) -> str:
    marker = "async def _fb_reservar_creacion("
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one _fb_reservar_creacion, found {source.count(marker)}")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        transformed = source.replace(OLD, NEW, 1)
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(f"Unexpected FB reserve POST state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
