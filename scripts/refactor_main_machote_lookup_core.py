#!/usr/bin/env python3
"""Route _machote_o_404's read through core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''async def _machote_o_404(machote_id: str, user_id: str, select: str = _MACHOTE_SELECT) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/machotes_contrato",
            headers=_sb_headers(),
            params={"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}",
                    "select": select, "limit": "1"},
        )
    if r.status_code != 200 or not r.json():
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    return r.json()[0]
'''

NEW = '''async def _machote_o_404(machote_id: str, user_id: str, select: str = _MACHOTE_SELECT) -> dict:
    try:
        rows = await get_rows(
            "machotes_contrato",
            {"id": f"eq.{machote_id}", "user_id": f"eq.{user_id}",
             "select": select, "limit": "1"},
            timeout=15,
        )
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    if not rows:
        raise HTTPException(status_code=404, detail="No encontramos ese machote.")
    return rows[0]
'''


def transform_source(source: str) -> str:
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 0 and new_count == 1:
        return source
    if old_count != 1 or new_count != 0:
        raise RuntimeError("Expected exactly one legacy or one Core _machote_o_404")
    return source.replace(OLD, NEW, 1)


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    transformed = transform_source(source)
    compile(transformed, str(MAIN), "exec")
    MAIN.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
