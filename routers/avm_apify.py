"""AVM comparables sourced from Apify/Inmuebles24."""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.cache import cache_get, cache_set
from core.config import settings


router = APIRouter()
APIFY_API_KEY = settings.apify_api_key
APIFY_ACTOR = "azzouzana~inmuebles24-scraper-pro-by-search-url"

TIPO_URL = {
    "casa": "casas",
    "departamento": "departamentos",
    "terreno": "terrenos",
    "local": "locales-comerciales",
    "oficina": "oficinas",
    "bodega": "bodegas",
    "edificio": "edificios",
}


class ComparablesRequest(BaseModel):
    colonia: str
    ciudad: str = "morelia"
    estado: str = "michoacan-de-ocampo"
    tipo: str = "casa"
    max_resultados: int = 10


def construir_url_inmuebles24(tipo: str, colonia: str, ciudad: str, estado: str) -> str:
    segmento = TIPO_URL.get(tipo, "casas")
    ciudad = ciudad.lower().strip().replace(" ", "-")
    col = colonia.lower().strip().replace(" ", "-")
    return f"https://www.inmuebles24.com/{segmento}-en-{ciudad}-o-{col}.html"


def normalizar_listing(item: dict) -> dict:
    """Convierte un resultado de Apify al formato histórico que espera el AVM."""
    precio = item.get("price_amount") or 0
    moneda = item.get("price_currency", "MN")
    if moneda == "USD":
        return None

    m2c = 0
    titulo_gen = item.get("generatedTitle", "")
    match_m2 = re.search(r'(\d+)m²', titulo_gen)
    if match_m2:
        m2c = float(match_m2.group(1))

    recamaras = 0
    match_rec = re.search(r'(\d+)\s+Rec[áa]maras?', titulo_gen, re.IGNORECASE)
    if match_rec:
        recamaras = int(match_rec.group(1))

    estac = 0
    match_estac = re.search(r'(\d+)\s+Estacionamientos?', titulo_gen, re.IGNORECASE)
    if match_estac:
        estac = int(match_estac.group(1))

    m2t = 0
    desc = item.get("descriptionNormalized", "")
    patrones_terreno = [
        r'[Tt]erreno[:\s/]+(\d+[\.,]?\d*)\s*(?:m²|m2|metros cuadrados|metros)',
        r'(\d+[\.,]?\d*)\s*(?:m²|m2)\s*de\s+terreno',
        r'[Ss]uperficie\s+de\s+terreno[:\s]+[\d,\s]*(\d+)\s*(?:m²|m2)',
        r'[Tt]erreno\s+de\s+(\d+[\.,]?\d*)\s*(?:m²|m2)',
    ]
    for patron in patrones_terreno:
        match_t = re.search(patron, desc)
        if match_t:
            val = match_t.group(1).replace(',', '').replace('.', '')
            try:
                m2t = float(val)
                if m2t < 10 or m2t > 50000:
                    m2t = 0
            except:
                m2t = 0
            if m2t > 0:
                break

    titulo = item.get("title") or ""
    url = item.get("url") or ""
    imagenes = item.get("images", [])
    imagen = imagenes[0].split("?")[0] if imagenes else ""

    return {
        "precio": int(precio),
        "m2Construccion": m2c,
        "m2Terreno": m2t,
        "recamaras": recamaras,
        "banos": 0,
        "estacionamiento": estac,
        "edad": 0,
        "conservacion": "bueno",
        "calidad": "medio",
        "mismaZona": "si",
        "titulo": titulo,
        "url": url,
        "imagen": imagen,
    }


@router.post("/api/comparables")
async def buscar_comparables(req: ComparablesRequest):
    """Llama a Apify y regresa comparables normalizados listos para el AVM."""
    if not APIFY_API_KEY:
        raise HTTPException(status_code=500, detail="APIFY_API_KEY no configurada en el servidor")

    url_busqueda = construir_url_inmuebles24(req.tipo, req.colonia, req.ciudad, req.estado)
    cache_key = f"comparables_{req.tipo}_{req.colonia}_{req.ciudad}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    apify_url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
        f"/run-sync-get-dataset-items?token={APIFY_API_KEY}"
        f"&timeout=60&memory=256"
    )
    payload = {"startUrl": url_busqueda, "maxItems": req.max_resultados}

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            r = await client.post(apify_url, json=payload)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Apify tardó demasiado. Intenta de nuevo.")

        if r.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Error de Apify: {r.status_code} — {r.text[:300]}",
            )
        items = r.json()

    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Respuesta inesperada de Apify")

    comparables = []
    for item in items:
        n = normalizar_listing(item)
        if n["precio"] > 0 and n["m2Construccion"] > 0:
            comparables.append(n)

    resultado = {
        "url_busqueda": url_busqueda,
        "total": len(comparables),
        "comparables": comparables,
    }
    cache_set(cache_key, resultado, ttl=7200)
    return resultado
