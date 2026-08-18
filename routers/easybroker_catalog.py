"""Legacy read-only EasyBroker catalog endpoints."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from core.easybroker import EB_API_KEY, EB_BASE, eb_headers


router = APIRouter()


@router.get("/propiedades")
async def get_propiedades(page: int = 1, limit: int = 20):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{EB_BASE}/properties",
            headers=eb_headers(),
            params={"page": page, "limit": limit},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()
