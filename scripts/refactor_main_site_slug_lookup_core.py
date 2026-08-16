#!/usr/bin/env python3
"""Route public site slug lookup through Core without touching lead writes."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''        # 1) Resolver el slug → agente dueño del sitio (solo sitios activos)
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios", headers=hdr,
            params={"slug": f"eq.{slug}", "sitio_activo": "eq.true",
                    "select": "id", "limit": "1"})
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
        user_id = rows[0]["id"]
'''

NEW = '''        # 1) Resolver el slug → agente dueño del sitio (solo sitios activos)
        try:
            rows = await get_rows(
                "usuarios",
                {"slug": f"eq.{slug}", "sitio_activo": "eq.true",
                 "select": "id", "limit": "1"},
                timeout=10,
            )
        except httpx.HTTPStatusError:
            rows = []
        if not rows:
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
        user_id = rows[0]["id"]
'''


def transform_source(source: str) -> str:
    start = source.index('@app.post("/sitio/{slug}/lead")')
    block = source[start:]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core public site slug lookup")
    return source[:start] + block.replace(OLD, NEW, 1)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
