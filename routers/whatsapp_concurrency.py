"""Bounded per-conversation locks for WhatsApp background processing."""
from __future__ import annotations


def lock_conv(conversacion_id: str, *, _LOCKS, asyncio):
    lock = _LOCKS.get(conversacion_id)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[conversacion_id] = lock
        if len(_LOCKS) > 5000:  # no dejar que crezca para siempre
            for k in list(_LOCKS.keys())[:1000]:
                if not _LOCKS[k].locked():
                    _LOCKS.pop(k, None)
    return lock
