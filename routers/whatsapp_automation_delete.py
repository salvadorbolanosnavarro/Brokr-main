from __future__ import annotations


async def wa2_automatizacion_delete_core(auto_id: str, request, *, _require_user,
                                         _ids_visibles, sb_delete, _in_filter):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    await sb_delete("wa2_automatizaciones", {"id": f"eq.{auto_id}", "user_id": _in_filter(ids)})
    return {"ok": True}
