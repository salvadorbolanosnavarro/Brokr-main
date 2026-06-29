"""Compatibility shim for the Broq agent router.

The active implementation lives in ``routers/agente.py`` and is mounted from
``main.py``. Keeping this thin module prevents the legacy root-level copy from
drifting out of sync with the real router.
"""

from routers.agente import router  # re-export for any legacy importers

__all__ = ["router"]
