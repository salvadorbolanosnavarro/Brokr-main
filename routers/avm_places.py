"""AVM colonia lookup backed by Google Places.

Devuelve colonia + ciudad + estado en una sola sugerencia: antes el
frontend pedía la colonia aquí pero la ciudad y el estado se capturaban
por separado (la ciudad en un campo de texto libre sin relación con
ningún estado, y el estado ni siquiera se pedía — quedaba fijo en el
default del backend). Eso permitía combinaciones geográficamente
imposibles como "Guadalajara, Michoacán". Ahora se sacan los tres datos
del mismo resultado de Google Places (address_components), así que una
sola selección deja colonia/ciudad/estado siempre consistentes entre sí.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter

from core.cache import cache_get, cache_set
from core.config import settings


router = APIRouter()
GOOGLE_PLACES_KEY = settings.google_places_key

# Google devuelve el nombre oficial largo de varios estados (el que usan
# leyes y actas de nacimiento), pero nadie busca inmuebles así. Normaliza
# a los nombres cortos de uso común para que las queries de búsqueda y la
# UI se vean como los escribiría un agente inmobiliario mexicano.
ESTADO_NOMBRE_CORTO = {
    "Michoacán de Ocampo": "Michoacán",
    "Veracruz de Ignacio de la Llave": "Veracruz",
    "Coahuila de Zaragoza": "Coahuila",
    "México": "Estado de México",  # administrative_area_level_1 para el Edomex es "México" a secas
    "Ciudad de México": "Ciudad de México",
}


def _extraer_ubicacion(address_components):
    """Saca ciudad y estado de los address_components de un Place Details."""
    ciudad = ""
    ciudad_fallback = ""
    estado = ""
    for comp in address_components or []:
        tipos = comp.get("types", [])
        nombre = comp.get("long_name", "")
        if "locality" in tipos and not ciudad:
            ciudad = nombre
        elif "administrative_area_level_2" in tipos and not ciudad_fallback:
            # Municipio — se usa solo si Google no dio "locality" (pasa en
            # zonas rurales o municipios chicos sin ciudad principal definida).
            ciudad_fallback = nombre
        elif "administrative_area_level_1" in tipos:
            estado = ESTADO_NOMBRE_CORTO.get(nombre, nombre)
    return (ciudad or ciudad_fallback), estado


# Con "types": "geocode" Google compite colonias contra domicilios completos
# (calle + número) por los mismos ~5 lugares de la respuesta de Autocomplete
# — el límite de resultados lo pone Google, no nosotros. Para un texto como
# "Cha" en Morelia, direcciones de la calle "Chapultepec" le ganaban el lugar
# a la colonia "Chapultepec" en sí. "(regions)" es la colección que Google
# documenta para restringir Autocomplete a locality/sublocality/postal_code/
# administrative_area — nunca a domicilios ni negocios — así los ~5 lugares
# que regresa ya son casi puras colonias, municipios y CPs candidatos.
#
# Aun con eso, Google no siempre etiqueta un fraccionamiento mexicano como
# "sublocality"/"neighborhood": muchos (sobre todo los privados, chicos o
# poco documentados) llegan como "administrative_area_level_3/4" o nomás
# "political" sin nada más específico. El filtro viejo exigía una lista
# corta de tipos exactos y tiraba todo lo demás — de ahí colonias obvias que
# nunca aparecían aunque Google sí las hubiera regresado. Ahora se acepta
# cualquier resultado que NO sea claramente ciudad/municipio/estado/país/CP,
# en vez de exigir que sí sea explícitamente colonia.
_TIPOS_DEMASIADO_AMPLIOS = {
    "locality", "administrative_area_level_1", "administrative_area_level_2",
    "country", "postal_code",
}


@router.get("/api/colonias")
async def buscar_colonias(texto: str):
    if len(texto) < 3:
        return {"colonias": []}

    cache_key = f"colonias_g5_{texto}".lower()
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
                    "types": "(regions)",
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

        if any(t in tipos for t in _TIPOS_DEMASIADO_AMPLIOS):
            continue

        nombre = pred.get("structured_formatting", {}).get("main_text", "").strip()
        place_id = pred.get("place_id", "")

        lat, lon = 0.0, 0.0
        ciudad, estado = "", ""
        if place_id:
            try:
                async with httpx.AsyncClient(timeout=10) as client2:
                    r2 = await client2.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={
                            "place_id": place_id,
                            "fields": "geometry,address_component",
                            "key": GOOGLE_PLACES_KEY,
                        },
                    )
                    details_data = r2.json()
                    result = details_data.get("result", {}) or {}
                    loc = result.get("geometry", {}).get("location", {})
                    lat = loc.get("lat", 0.0)
                    lon = loc.get("lng", 0.0)
                    ciudad, estado = _extraer_ubicacion(result.get("address_components"))
            except Exception:
                pass

        if nombre:
            colonias.append({
                "nombre": nombre,
                "display": descripcion,
                "ciudad": ciudad,
                "estado": estado,
                "latitud": lat,
                "longitud": lon,
                "place_id": place_id,
            })

    resultado = {"colonias": colonias[:6]}
    cache_set(cache_key, resultado, ttl=86400)
    return resultado
