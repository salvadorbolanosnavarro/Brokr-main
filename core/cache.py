"""Small process-local TTL cache used by legacy Broquer endpoints."""
from __future__ import annotations

import time
from typing import Any


_CACHE: dict[Any, tuple[Any, float]] = {}
_CACHE_TTL_SECONDS = 21600  # 6 hours default
_CACHE_TTL_OVERRIDES: dict[Any, int | float] = {}


def cache_get(key):
    if key in _CACHE:
        data, ts = _CACHE[key]
        ttl = _CACHE_TTL_OVERRIDES.get(key, _CACHE_TTL_SECONDS)
        if time.time() - ts < ttl:
            return data
        del _CACHE[key]
        _CACHE_TTL_OVERRIDES.pop(key, None)
    return None


def cache_set(key, data, ttl=None):
    _CACHE[key] = (data, time.time())
    if ttl is not None:
        _CACHE_TTL_OVERRIDES[key] = ttl
