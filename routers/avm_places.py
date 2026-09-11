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

import asyncio

import httpx
from fastapi import APIRouter

from core.cache import cache_get, cache_set
from core.config import settings


router = APIRouter()
GOOGLE_PLACES_KEY = settings.google_places_key

AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Círculo alrededor de Morelia (donde opera el negocio). Cubre la ciudad y
# sus fraccionamientos periféricos (Altozano, Vistas Altozano, etc. están
# a ~10-15 km del centro) sin llegar a alcanzar otro estado — el Edomex más
# cercano queda a ~100 km, así que un "strictbounds" con este radio no se
# confunde con colonias homónimas de otras entidades.
_LOCATIONBIAS = "circle:50000@19.7059504,-101.1949825"

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


# Por qué NO se restringe "types" en la búsqueda:
#   Una versión anterior mandaba "types": "(regions)" para que Google dejara
#   de competir colonias contra domicilios completos por los mismos ~5
#   lugares de la respuesta. Funcionó para eso, pero rompió algo peor:
#   "(regions)" excluye de raíz cualquier resultado que Google clasifique
#   como establecimiento/punto de interés — y varios fraccionamientos
#   grandes de Morelia (Altozano es el ejemplo que ya usa el placeholder
#   del campo: "Ej: Vistas Altozano, Morelia...") Google los indexa
#   primero por su plaza/desarrollo comercial, como "point_of_interest" o
#   "establishment", no como "sublocality". Con "(regions)", Altozano no
#   aparecía NUNCA sin importar cuánto se escribiera. Ahora no se restringe
#   el tipo de búsqueda — se acepta cualquier tipo de resultado — y el
#   filtro de abajo solo descarta lo que es inequívocamente demasiado
#   amplio (ciudad/municipio/estado/país/CP) o un domicilio puntual
#   (calle/número), nunca una zona o desarrollo con nombre propio.
_TIPOS_EXCLUIDOS = {
    "locality", "administrative_area_level_1", "administrative_area_level_2",
    "country", "postal_code",
    "route", "street_address", "premise", "subpremise",
}

# Cuántos candidatos (ya sin duplicados) se les pide detalle a Google como
# máximo, antes de recortar a los primeros 6 que se le muestran al usuario.
# Un poco de margen sobre 6 para que el recorte final elija entre varios,
# no exactamente los primeros que hayan pasado el filtro de tipos.
_MAX_CANDIDATOS = 10


def _combinar_candidatos(locales: list[dict], nacionales: list[dict], *, max_candidatos: int = _MAX_CANDIDATOS) -> list[dict]:
    """Une las dos respuestas de Autocomplete: sin duplicar por place_id, sin
    los tipos demasiado amplios, y con lo local primero. Aparte de
    ``_autocomplete`` para poder probar la mezcla sin llamar a Google.
    """
    vistos = set()
    candidatos = []
    for pred in locales + nacionales:
        place_id = pred.get("place_id")
        if not place_id or place_id in vistos:
            continue
        tipos = pred.get("types", [])
        if any(t in tipos for t in _TIPOS_EXCLUIDOS):
            continue
        vistos.add(place_id)
        candidatos.append(pred)
        if len(candidatos) >= max_candidatos:
            break
    return candidatos


async def _autocomplete(client: httpx.AsyncClient, texto: str, *, strictbounds: bool) -> list[dict]:
    """Una llamada a Autocomplete. Nunca lanza — una falla aquí no debe tirar
    la búsqueda completa si la otra llamada sí funcionó."""
    params = {
        "input": texto,
        "language": "es",
        "components": "country:mx",
        "locationbias": _LOCATIONBIAS,
        "key": GOOGLE_PLACES_KEY,
    }
    if strictbounds:
        # A diferencia de "locationbias" (una preferencia suave que Google
        # puede ignorar si hay una coincidencia de texto más fuerte fuera de
        # la zona), "strictbounds" sí descarta cualquier resultado fuera del
        # círculo. Por eso esta llamada garantiza que, si existe una colonia
        # local con ese nombre, esté en los resultados — no depende de que
        # le gane en relevancia a una tocaya de otro estado (p.ej. una
        # colonia "Jesús del Monte" en la Ciudad de México o el Edomex
        # ganándole el lugar a la "Jesús del Monte" real de Morelia).
        params["strictbounds"] = "true"
    try:
        r = await client.get(AUTOCOMPLETE_URL, params=params)
        return r.json().get("predictions") or []
    except Exception:
        return []


@router.get("/api/colonias")
async def buscar_colonias(texto: str):
    if len(texto) < 3:
        return {"colonias": []}

    cache_key = f"colonias_g6_{texto}".lower()
    cached = cache_get(cache_key)
    if cached:
        return cached

    if not GOOGLE_PLACES_KEY:
        return {"colonias": [], "error": "GOOGLE_PLACES_KEY no configurada"}

    # Dos llamadas en paralelo: una estricta a la zona de Morelia (garantiza
    # que lo local aparezca) y otra con sesgo suave a nivel nacional (para
    # cuando el inmueble está en otra ciudad). Se combinan sin duplicar,
    # con lo local primero.
    async with httpx.AsyncClient(timeout=15) as client:
        locales, nacionales = await asyncio.gather(
            _autocomplete(client, texto, strictbounds=True),
            _autocomplete(client, texto, strictbounds=False),
        )

    candidatos = _combinar_candidatos(locales, nacionales)

    colonias = []
    for pred in candidatos:
        descripcion = pred.get("description", "")
        nombre = pred.get("structured_formatting", {}).get("main_text", "").strip()
        place_id = pred.get("place_id", "")

        lat, lon = 0.0, 0.0
        ciudad, estado = "", ""
        if place_id:
            try:
                async with httpx.AsyncClient(timeout=10) as client2:
                    r2 = await client2.get(
                        DETAILS_URL,
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
