#!/usr/bin/env python3
"""Route _fb_buscar_dueno_de_pagina user_integrations reads through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_integrations",
                headers=_sb_headers(),
                params={"provider": "eq.facebook",
                        "select": "user_id,org_id,api_key,meta",
                        "meta": f"like.*{page_id}*",
                        "limit": "20"})
            filas = r.json() if r.status_code == 200 else []
            if not filas:
                # Respaldo: si el LIKE no aplica (columna jsonb), se revisa todo.
                r2 = await client.get(
                    f"{SUPABASE_URL}/rest/v1/user_integrations",
                    headers=_sb_headers(),
                    params={"provider": "eq.facebook",
                            "select": "user_id,org_id,api_key,meta", "limit": "500"})
                filas = r2.json() if r2.status_code == 200 else []
    except Exception as e:
'''

NEW = '''    try:
        try:
            filas = await get_rows(
                "user_integrations",
                {"provider": "eq.facebook",
                 "select": "user_id,org_id,api_key,meta",
                 "meta": f"like.*{page_id}*",
                 "limit": "20"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            filas = []
        if not filas:
            # Respaldo: si el LIKE no aplica (columna jsonb), se revisa todo.
            try:
                filas = await get_rows(
                    "user_integrations",
                    {"provider": "eq.facebook",
                     "select": "user_id,org_id,api_key,meta", "limit": "500"},
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                filas = []
    except Exception as e:
'''


def transform_source(source: str) -> str:
    start = source.index("async def _fb_buscar_dueno_de_pagina(page_id: str) -> dict:")
    end = source.index("# Cómo se llaman los campos estándar de Meta", start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core page-owner read block")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
