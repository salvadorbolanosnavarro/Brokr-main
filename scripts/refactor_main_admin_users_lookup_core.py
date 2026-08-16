#!/usr/bin/env python3
"""Route admin_list_users' initial usuarios read through Core only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # 1) Traer todos los usuarios
    async with httpx.AsyncClient(timeout=15) as client:
        r_users = await client.get(
            f"{SUPABASE_URL}/rest/v1/usuarios",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            params={
                "select": "id,email,nombre,telefono,rol,activo,created_at",
                "order": "created_at.desc",
                "limit": "10000",
            },
        )
    if r_users.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Error listando usuarios: {r_users.text}")
    users = r_users.json()
'''

NEW = '''    # 1) Traer todos los usuarios
    try:
        users = await get_rows(
            "usuarios",
            {
                "select": "id,email,nombre,telefono,rol,activo,created_at",
                "order": "created_at.desc",
                "limit": "10000",
            },
            timeout=15,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")
'''


def transform_source(source: str) -> str:
    start = source.index('@app.get("/admin/users")')
    end = source.index('class AdminRolReq(BaseModel):', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core admin users lookup")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
