"""WhatsApp 2 domain-specific database compatibility adapters.

These wrappers intentionally preserve the legacy fail-soft/retry policies from
whatsapp.py while delegating all PostgREST I/O to shared Core primitives.
"""
from __future__ import annotations

import logging

import httpx

from core.database import delete_rows, get_rows, patch_rows, post_rows


log = logging.getLogger("broquer.whatsapp2")


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
