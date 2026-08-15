#!/usr/bin/env python3
"""Route main.py authentication through core.auth without changing callers."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"

OLD_IMPORT_BLOCK = '''from pydantic import BaseModel
from core.config import settings
import httpx
'''
NEW_IMPORT_BLOCK = '''from pydantic import BaseModel
from core.auth import get_user_id_from_token
from core.config import settings
import httpx
'''

OLD_AUTH_HELPER = '''# Helper: extrae el user_id del token de Supabase
async def get_user_id_from_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("id")
    except Exception:
        pass
    return None

'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"main.py {label} block does not match reviewed source")
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    if "from core.auth import get_user_id_from_token" in text:
        raise RuntimeError("main auth refactor already appears applied")
    text = _replace_once(text, OLD_IMPORT_BLOCK, NEW_IMPORT_BLOCK, "Core auth import")
    text = _replace_once(text, OLD_AUTH_HELPER, "", "legacy auth helper")
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "main.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
