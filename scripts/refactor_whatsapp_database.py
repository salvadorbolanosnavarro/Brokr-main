#!/usr/bin/env python3
"""Route WhatsApp 2 table access through core.database while preserving retries."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"

OLD_IMPORT = '''from core.auth import require_user_id
from core.config import settings
'''
NEW_IMPORT = '''from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers
'''

HELPERS_START = '''# =============================================================================
# Helpers de Supabase (REST) — con reintento ante timeout/5xx, igual patrón
# probado que el resto del backend, pero self-contained en este archivo.
# =============================================================================
'''
HELPERS_END = '''async def _require_user(request: Request) -> str:
'''

NEW_HELPERS = '''# =============================================================================
# Helpers de Supabase — compatibilidad sobre Core
# =============================================================================
def _sb_headers() -> dict:
    # Temporary adapter for non-table Supabase calls (for example Storage).
    # Credential policy itself lives in core.database.
    return service_headers()


async def sb_get(table: str, params: dict) -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            return await get_rows(table, params, timeout=15)
        except httpx.HTTPStatusError as exc:
            r = exc.response
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_get %s falló -> %s", table, ultimo)
    return []


async def sb_post(table: str, body: dict, prefer: str = "return=representation") -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            return await post_rows(table, body, prefer=prefer, timeout=15)
        except httpx.HTTPStatusError as exc:
            r = exc.response
            if r.status_code == 409:
                log.info("sb_post %s: la fila ya existe (409).", table)
                return []
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_post %s falló -> %s", table, ultimo)
    return []


async def sb_patch(table: str, params: dict, body: dict) -> list:
    ultimo = ""
    for intento in (1, 2):
        try:
            return await patch_rows(
                table,
                params,
                body,
                prefer="return=representation",
                timeout=15,
            )
        except httpx.HTTPStatusError as exc:
            r = exc.response
            ultimo = f"{r.status_code}: {r.text[:300]}"
            if r.status_code < 500:
                break
        except Exception as e:
            ultimo = str(e)
    log.error("sb_patch %s falló -> %s", table, ultimo)
    return []


async def sb_delete(table: str, params: dict) -> bool:
    try:
        await delete_rows(table, params, timeout=15)
        return True
    except Exception as e:
        log.error("sb_delete %s falló -> %s", table, e)
        return False


'''


def transform(text: str) -> str:
    if "from core.database import delete_rows, get_rows, patch_rows, post_rows, service_headers" in text:
        raise RuntimeError("WhatsApp database refactor already appears applied")
    if text.count(OLD_IMPORT) != 1:
        raise RuntimeError("WhatsApp Core import block does not match reviewed source")
    if text.count(HELPERS_START) != 1 or text.count(HELPERS_END) != 1:
        raise RuntimeError("WhatsApp Supabase helper block does not match reviewed source")

    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)
    start = text.index(HELPERS_START)
    end = text.index(HELPERS_END, start)
    text = text[:start] + NEW_HELPERS + text[end:]
    return text


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    compile(updated, "whatsapp.py", "exec")
    TARGET.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
