"""Authenticated read-only EasyBroker property endpoints."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.easybroker import EB_BASE, eb_headers
from routers.easybroker_config import get_eb_key_for_user


router = APIRouter()


@router.get("/propiedad/{property_id}")
async def get_propiedad(property_id: str, request: Request):
    # Multi-tenant blindado: identificar al usuario por su token de Supabase
    # y sacar SU EB key del backend. La API key nunca toca el frontend.
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    user_key = await get_eb_key_for_user(user_id)
    if not user_key:
        raise HTTPException(
            status_code=400,
            detail="Configura tu API key de EasyBroker en Perfil → Integración EasyBroker para usar este módulo.",
        )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{EB_BASE}/properties/{property_id}",
            headers=eb_headers(user_key),
        )
        if r.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="Tu API key de EasyBroker fue rechazada. Reconéctala en Perfil → Integración EasyBroker.",
            )
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()
