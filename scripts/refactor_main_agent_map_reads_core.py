#!/usr/bin/env python3
"""Route _mapa_agentes_org's member/profile reads through Core."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    sb_headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            rm = await client.get(
                f"{SUPABASE_URL}/rest/v1/organizacion_miembros",
                headers=sb_headers,
                params={"org_id": f"eq.{org_id}", "select": "user_id", "limit": "200"}
            )
            miembros = rm.json() if rm.status_code == 200 else []
            ids = [m["user_id"] for m in miembros if m.get("user_id")]
            if ids:
                ru = await client.get(
                    f"{SUPABASE_URL}/rest/v1/usuarios",
                    headers=sb_headers,
                    params={"id": f"in.({','.join(ids)})",
                            "select": "id,nombre,email", "limit": "200"}
                )
                for u in (ru.json() if ru.status_code == 200 else []):
                    uid = u.get("id")
                    if not uid:
                        continue
                    em = (u.get("email") or "").strip().lower()
                    if em:
                        por_email[em] = uid
                    nm = _nrm(u.get("nombre"))
                    if nm:
                        por_nombre[nm] = uid
    except Exception as e:
        print(f"[importar] No se pudo leer el mapa de agentes: {e}")
'''

NEW = '''    try:
        try:
            miembros = await get_rows(
                "organizacion_miembros",
                {"org_id": f"eq.{org_id}", "select": "user_id", "limit": "200"},
                timeout=15,
            )
        except httpx.HTTPStatusError:
            miembros = []
        ids = [m["user_id"] for m in miembros if m.get("user_id")]
        if ids:
            try:
                perfiles = await get_rows(
                    "usuarios",
                    {"id": f"in.({','.join(ids)})", "select": "id,nombre,email", "limit": "200"},
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                perfiles = []
            for u in perfiles:
                uid = u.get("id")
                if not uid:
                    continue
                em = (u.get("email") or "").strip().lower()
                if em:
                    por_email[em] = uid
                nm = _nrm(u.get("nombre"))
                if nm:
                    por_nombre[nm] = uid
    except Exception as e:
        print(f"[importar] No se pudo leer el mapa de agentes: {e}")
'''


def transform_source(source: str) -> str:
    start = source.index("async def _mapa_agentes_org(org_id: str, user_id: str) -> dict:")
    end = source.index('@app.post("/contactos/importar-eb")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core agent map read block")
    return source[:start] + block.replace(OLD, NEW, 1) + source[end:]


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
