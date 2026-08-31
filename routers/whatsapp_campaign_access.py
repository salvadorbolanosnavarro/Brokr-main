"""Tenant-scoped read access helpers for WhatsApp campaigns."""
from __future__ import annotations


async def _numero_visible_core(request, numero_id: str, *, _require_user, _ids_visibles,
                               sb_get, _in_filter, HTTPException) -> tuple[str, dict]:
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    rows = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}",
                                        "user_id": _in_filter(ids),
                                        "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    return user_id, rows[0]
