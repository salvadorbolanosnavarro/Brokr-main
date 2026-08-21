"""Bounded per-conversation locks for WhatsApp background processing."""
from __future__ import annotations

import asyncio


_LOCKS: dict[str, asyncio.Lock] = {}


def lock_conv(conversacion_id: str) -> asyncio.Lock:
    lock = _LOCKS.get(conversacion_id)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[conversacion_id] = lock
        if len(_LOCKS) > 5000:
            for key in list(_LOCKS.keys())[:1000]:
                if not _LOCKS[key].locked():
                    _LOCKS.pop(key, None)
    return lock
