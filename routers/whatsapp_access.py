"""Authentication and organization visibility rules for WhatsApp."""
from __future__ import annotations

from fastapi import Request

from core.auth import require_user_id
from routers.organizaciones import get_org_context
from routers.whatsapp_data import sb_get


async def _require_user(request: Request) -> str:
    return await require_user_id(request, detail="No autorizado")


async def _ids_visibles(user_id: str) -> list[str]:
    """Return the active user ids whose WhatsApp data the caller may inspect."""
    ctx = await get_org_context(user_id)
    if not ctx or not ctx.get("org_id") or ctx.get("rol_org") not in ("owner", "admin"):
        return [user_id]
    miembros = await sb_get("organizacion_miembros", {
        "org_id": f"eq.{ctx['org_id']}", "activo": "eq.true", "select": "user_id"})
    ids = {m["user_id"] for m in miembros if m.get("user_id")}
    ids.add(user_id)
    return list(ids)
