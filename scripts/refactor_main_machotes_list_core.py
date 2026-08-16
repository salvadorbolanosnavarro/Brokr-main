#!/usr/bin/env python3
"""Route GET /contrato/machotes through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers(),
            params={"user_id": f"eq.{user_id}",
                    "select": "id,titulo,tipo,campos,motor,created_at",
                    "order": "created_at.desc"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")
    return {"machotes": r.json() or []}
'''

NEW = '''    try:
        rows = await get_rows(
            "machotes_contrato",
            {"user_id": f"eq.{user_id}",
             "select": "id,titulo,tipo,campos,motor,created_at",
             "order": "created_at.desc"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")
    return {"machotes": rows}
'''


def transform_source(source: str) -> str:
    start = source.index('@app.get("/contrato/machotes")')
    end = source.index('@app.get("/contrato/machote/{machote_id}")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core machotes list read")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
