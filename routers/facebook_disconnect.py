"""Static extraction of the Facebook disconnect endpoint."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from core.database import delete_rows
from routers.organizaciones import exigir_gestion_integraciones


router = APIRouter()


@router.delete("/facebook/connection")
async def facebook_disconnect(request: Request):
    """Elimina la conexión de Facebook de la EMPRESA en Supabase.
    Deja al equipo entero sin anuncios: solo el dueño o quien él designe."""
    user_id = await exigir_gestion_integraciones(request)
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status_code=500, detail="Supabase no configurado")
    try:
        await delete_rows(
            "user_integrations",
            {"user_id": f"eq.{user_id}", "provider": "eq.facebook"},
            timeout=10,
        )
    except httpx.HTTPStatusError:
        # Historical behavior: HTTP rejection was ignored; transport failures
        # still propagate.
        pass
    return {"ok": True}
