"""Shared bounded executors for legacy CPU/blocking work during decomposition."""
from __future__ import annotations

import concurrent.futures


# Preserve main.py's historical global executor size and sharing semantics.
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
