"""AVM comparables nearby through Supabase/PostGIS."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.cache import cache_get, cache_set
from core.config import settings
from core.database import call_public_rpc, get_public_rows


router = APIRouter()


class CercanosRequest(BaseModel):
    latitud: float
    longitud: float
    tipo: str = "casa"
    radio_km: float = 2.0
    max_resultados: int = 15


TIPO_MAP_DB = {
    "casa":         ["Casas", "Desarrollos horizontales", "Desarrollos Horizontal/Vertical"],
    "departamento": ["Departamentos", "Desarrollos verticales"],
    "terreno":      ["Terrenos"],
    "local":        ["Locales comerciales", "Locales Comerciales"],
    "oficina":      ["Oficinas"],
    "bodega":       ["Bodegas"],
    "edificio":     ["Edificios"],
}


@router.post("/api/comparables-cercanos")
async def comparables_cercanos(req: CercanosRequest):
    """Busca propiedades cercanas en Supabase usando PostGIS."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="SUPABASE_URL o SUPABASE_ANON_KEY no configuradas")

    cache_key = f"cercanos_{req.tipo}_{req.latitud:.4f}_{req.longitud:.4f}_{req.radio_km}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    tipos_db = TIPO_MAP_DB.get(req.tipo, ["Casas"])
    radio_metros = int(req.radio_km * 1000)
    payload = {
        "lat": req.latitud,
        "lon": req.longitud,
        "radio": radio_metros,
        "tipos": tipos_db,
        "limite": req.max_resultados,
    }

    try:
        items = await call_public_rpc(
            "buscar_cercanos",
            payload,
            timeout=15,
            accepted_statuses=(200, 201),
        ) or []
    except httpx.HTTPStatusError:
        try:
            items = await get_public_rows(
                "propiedades_avm",
                {
                    "ciudad": "eq.Morelia",
                    "precio": "gt.0",
                    "metros_construccion": "not.is.null",
                    "select": "id,titulo,precio,tipo_propiedad,metros_construccion,metros_terreno,recamaras,estacionamientos,colonia,ciudad,url,latitud,longitud",
                    "limit": req.max_resultados,
                    "order": "precio.asc",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError:
            items = []

    comparables = []
    for item in items:
        precio = item.get("precio") or 0
        m2c = item.get("metros_construccion") or 0
        if precio <= 0 or m2c <= 0:
            continue
        comparables.append({
            "precio": int(precio),
            "m2Construccion": float(m2c),
            "m2Terreno": float(item.get("metros_terreno") or 0),
            "recamaras": int(item.get("recamaras") or 0),
            "estacionamiento": int(item.get("estacionamientos") or 0),
            "banos": 0,
            "edad": 0,
            "conservacion": "bueno",
            "calidad": "medio",
            "mismaZona": "si",
            "titulo": item.get("titulo") or "",
            "url": item.get("url") or "",
            "imagen": "",
            "colonia": item.get("colonia") or "",
            "distancia_metros": int(item.get("distancia_metros") or 0),
        })

    resultado = {
        "total": len(comparables),
        "comparables": comparables,
        "latitud": req.latitud,
        "longitud": req.longitud,
        "radio_km": req.radio_km,
    }
    cache_set(cache_key, resultado, ttl=3600)
    return resultado
