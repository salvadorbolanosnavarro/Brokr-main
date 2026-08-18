"""AVM colonia lookup backed by Google Places."""
from __future__ import annotations

import httpx
from fastapi import APIRouter

from core.cache import cache_get, cache_set
from core.config import settings


router = APIRouter()
GOOGLE_PLACES_KEY = settings.google_places_key


@router.get("/api/colonias")
async def buscar_colonias(texto: str, ciudad: str = "Morelia"):
    if len(texto) < 3:
        return {"colonias": []}

    cache_key = f"colonias_g3_{ciudad}_{texto}".lower()
    cached = cache_get(cache_key)
    if cached:
        return cached

    if not GOOGLE_PLACES_KEY:
        return {"colonias": [], "error": "GOOGLE_PLACES_KEY no configurada"}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params={
                    "input": texto,
                    "types": "geocode",
                    "language": "es",
                    "components": "country:mx",
                    "locationbias": "circle:50000@19.7059504,-101.1949825",
                    "key": GOOGLE_PLACES_KEY,
                },
            )
            data = r.json()
        except Exception as e:
            return {"colonias": [], "error": str(e)}

    colonias = []
    for pred in data.get("predictions", []):
        descripcion = pred.get("description", "")
        tipos = pred.get("types", [])

        if not any(t in tipos for t in ["sublocality", "sublocality_level_1", "neighborhood"]):
            continue

        nombre = pred.get("structured_formatting", {}).get("main_text", "").strip()
        place_id = pred.get("place_id", "")

        lat, lon = 0.0, 0.0
        if place_id:
            try:
                async with httpx.AsyncClient(timeout=10) as client2:
                    r2 = await client2.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place_id,
                            "fields": "geometry",
                            "key": GOOGLE_PLACES_KEY,
                        },
                    )
                    details_data = r2.json()
                    loc = details_data.get("result", {}).get("geometry", {}).get("location", {})
                    lat = loc.get("lat", 0.0)
                    lon = loc.get("lng", 0.0)
            except Exception:
                pass

        if nombre:
            colonias.append({
                "nombre": nombre,
                "display": descripcion,
                "latitud": lat,
                "longitud": lon,
                "place_id": place_id,
            })

    resultado = {"colonias": colonias[:6]}
    cache_set(cache_key, resultado, ttl=86400)
    return resultado
