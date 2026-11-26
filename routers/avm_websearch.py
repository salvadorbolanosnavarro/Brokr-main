"""Búsqueda web de anuncios inmobiliarios y lectura segura (SSRF) de páginas
públicas de portales.

La usan el ACM (routers/acm_datos.py) y el Buscador de propiedades
(routers/buscador_propiedades.py). La valuación con IA que vivía aquí (el AVM
viejo) se retiró: los valores los calcula core/acm_calculo.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from core.cache import cache_get, cache_set
from core.config import settings
from core.database import rest_url, service_headers
from core.easybroker import normalize as _normalize_colonia
from core.http import fetch_public_http_result
from core.legacy_main_config import legacy_main_settings
from core.paises import PAISES, PAIS_DEFAULT, datos_pais


GOOGLE_PLACES_KEY = settings.google_places_key


class AvmWebSearchRequest(BaseModel):
    colonia: str
    tipo_inmueble: str
    operacion: str = "venta"
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos: float = 0
    estacionamientos: int = 0
    condicion_terreno: str = ""
    # Sin default geográfico: antes "Morelia"/"Michoacán" se colaban en
    # silencio cuando el frontend no mandaba ciudad/estado (o los mandaba
    # desalineados), produciendo combinaciones imposibles como
    # "Guadalajara, Michoacán". Vacío es honesto; un valor concreto que
    # nadie pidió no lo es.
    ciudad: str = ""
    estado: str = ""
    comentarios: str = ""
    # Coordenadas de la colonia elegida (vienen del mismo resultado de
    # Google Places que ya trae ciudad/estado — ver routers/avm_places.py).
    # Con esto se pueden descubrir las colonias colindantes reales en vez
    # de depender de que el modelo "se acuerde" de la geografía de memoria.
    latitud: float = 0
    longitud: float = 0
    # País de la cuenta. Lo fija el servidor desde el perfil, no el navegador.
    pais: str = PAIS_DEFAULT
    # Búsqueda "en toda la ciudad con la misma superficie". El ACM la apaga:
    # trae anuncios de cualquier zona y sólo le sirven los de la colonia y sus
    # vecinas. El Buscador de propiedades la conserva.
    incluir_busqueda_ciudad: bool = True


SEARCH_TIMEOUT = legacy_main_settings.avm_search_timeout
FETCH_TIMEOUT = legacy_main_settings.avm_fetch_timeout
MAX_SEARCH_RESULTS = legacy_main_settings.avm_max_search_results
MAX_URLS_TO_FETCH = legacy_main_settings.avm_max_urls_to_fetch
MAX_TEXT_CHARS_PER_URL = legacy_main_settings.avm_max_text_chars_per_url

PORTAL_HINTS = {
    "inmuebles24.com": "Inmuebles24",
    "lamudi.com.mx": "Lamudi",
    "propiedades.com": "Propiedades.com",
    "vivanuncios.com.mx": "Vivanuncios",
    "icasas.mx": "iCasas",
    "trovit.com.mx": "Trovit",
    "easybroker.com": "EasyBroker",
    "metroscubicos.com": "Metros Cúbicos",
    "nestoria.mx": "Nestoria",
    "mercadolibre.com.mx": "Mercado Libre Inmuebles",
}
# Portales de Colombia, Perú, Argentina y Chile (core/paises.py).
for _cfg in PAISES.values():
    for _dominio, _nombre in _cfg["portales"].items():
        PORTAL_HINTS.setdefault(_dominio, _nombre)

BLOCKED_FETCH_DOMAINS = {
    "google.com", "google.com.mx", "facebook.com", "instagram.com", "tiktok.com",
    "youtube.com", "maps.google.com", "googleusercontent.com"
}

# Mensajes que ve la persona: sin nombres de herramientas ni proveedores (el
# detalle técnico va a los logs de Railway con el prefijo [avm]).
_MSG_NO_DISPONIBLE = "La búsqueda de comparables no está disponible en este momento. Intenta más tarde."

FIRECRAWL_API_KEY = legacy_main_settings.firecrawl_api_key
FIRECRAWL_CONCURRENCY = legacy_main_settings.firecrawl_concurrency
FIRECRAWL_TIMEOUT = legacy_main_settings.firecrawl_timeout
FIRECRAWL_STRUCTURED_EXTRACT = legacy_main_settings.firecrawl_structured_extract


def _log_firecrawl(mensaje: str) -> None:
    """Línea "[firecrawl] …" en los logs de Railway. Con flush para que salga
    al momento: sin él, Python guarda los print() en un búfer y la línea
    puede no aparecer nunca en los logs."""
    print(f"[firecrawl] {mensaje}", flush=True)


def estado_firecrawl() -> str:
    if FIRECRAWL_API_KEY:
        return "activo"
    return "inactivo: falta FIRECRAWL_API_KEY"


# Al arrancar el servidor (main.py importa este módulo al iniciar).
_log_firecrawl(estado_firecrawl())
AVM_CACHE_TTL_DAYS = legacy_main_settings.avm_cache_ttl_days

PREMIUM_FETCH_DOMAINS = {
    "inmuebles24.com",
    "lamudi.com.mx",
    "lamudi.com",
    "propiedades.com",
    "metroscubicos.com",
    "mercadolibre.com.mx",
    # Estos portales también bloquean el fetch directo con captcha/login
    # con bastante frecuencia (confirmado en producción: un AVM real donde
    # "todas las páginas devolvieron errores de acceso" y terminó en
    # confianza baja sin necesidad, porque nunca se les dio la oportunidad
    # de pasar por Firecrawl). easybroker.com se deja fuera a propósito:
    # es la plataforma propia de Broquer, no tiene el mismo bloqueo y no
    # vale la pena gastarle crédito de Firecrawl de entrada.
    "vivanuncios.com.mx",
    "icasas.mx",
    "trovit.com.mx",
    "nestoria.mx",
}


# La extracción estructurada pide una LISTA de anuncios, no uno solo. Antes
# el esquema era un objeto plano (un precio, una superficie): en una página
# de resultados con 20 locales Firecrawl devolvía uno al azar o ninguno, y
# el modelo, con la advertencia de multi-listado encima, terminaba sin
# comparables aunque la página trajera la oferta completa de la zona.
# (Caso real: 14 páginas leídas sin errores → solo 2 comparables.)
_FIRECRAWL_LISTING_PROMPT = (
    "Extrae TODOS los anuncios inmobiliarios individuales que aparezcan en "
    "esta página. Si es el detalle de un solo anuncio, devuelve una lista con "
    "ese único anuncio. Si es una página de resultados o listado, devuelve un "
    "elemento por cada anuncio visible. Para cada anuncio: título, ubicación "
    "(colonia/calle tal como aparece), operación (venta o renta), precio (solo "
    "el número, sin símbolos de moneda ni separadores), moneda, superficie de "
    "terreno en m2, superficie de construcción en m2, recámaras, baños, "
    "estacionamientos y la liga (URL) del anuncio individual. Si un dato no "
    "aparece explícitamente para ESE anuncio, omite el campo — nunca inventes "
    "ni adivines un valor, y nunca mezcles datos de anuncios distintos. No "
    "incluyas anuncios sin precio."
)

_FIRECRAWL_LISTING_SCHEMA = {
    "type": "object",
    "properties": {
        "anuncios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "ubicacion": {"type": "string"},
                    "operacion": {"type": "string"},
                    "precio": {"type": "number"},
                    "moneda": {"type": "string"},
                    "m2_terreno": {"type": "number"},
                    "m2_construccion": {"type": "number"},
                    "recamaras": {"type": "number"},
                    "banos": {"type": "number"},
                    "estacionamientos": {"type": "number"},
                    "url": {"type": "string"},
                },
            },
        },
    },
}

# Encabezado del bloque estructurado dentro de page_text. Sin el nombre de
# la herramienta: este texto llega al modelo y podría repetirlo.
MARCA_ANUNCIOS = "ANUNCIOS ESTRUCTURADOS DE LA PÁGINA"
MAX_ANUNCIOS_POR_PAGINA = 30
# El bloque estructurado tiene su propio presupuesto de caracteres: antes
# compartía el recorte con el markdown y podía comerse el texto de la página.
MAX_STRUCT_CHARS = 6000
# Tope total de page_text (bloque estructurado + advertencia + markdown).
MAX_PAGE_TEXT_CHARS = MAX_TEXT_CHARS_PER_URL + MAX_STRUCT_CHARS + 1200

_CAMPOS_ANUNCIO = ("precio", "moneda", "operacion", "m2_construccion", "m2_terreno",
                   "recamaras", "banos", "estacionamientos")


def _limpia_campo(valor: Any) -> str:
    return _sameish_text(str(valor)).replace("|", "/")[:140]


def _anuncios_estructurados(datos: Any) -> List[Dict[str, Any]]:
    """Normaliza la respuesta "json" de Firecrawl a una lista de anuncios.
    Acepta el formato actual ({"anuncios": [...]}) y el anterior (un solo
    anuncio como objeto plano)."""
    if not isinstance(datos, dict):
        return []
    lista = datos.get("anuncios")
    if isinstance(lista, list):
        return [a for a in lista if isinstance(a, dict)]
    if datos.get("precio") not in (None, ""):
        return [datos]
    return []


def _formatea_estructurado_firecrawl(datos: Dict[str, Any], url_pagina: str = "") -> str:
    """Bloque de alta confianza que el prompt de valuación (regla 10) lee
    antes que el texto libre: un anuncio por línea, cada uno con su propio
    precio y superficie, para que una página de listado rinda un comparable
    por anuncio en vez de ninguno."""
    from urllib.parse import urljoin

    lineas: List[str] = []
    vistos = set()
    for anuncio in _anuncios_estructurados(datos):
        precio = anuncio.get("precio")
        if precio in (None, "", 0):
            continue
        partes: List[str] = []
        for campo in ("titulo", "ubicacion"):
            if anuncio.get(campo):
                partes.append(_limpia_campo(anuncio[campo]))
        for campo in _CAMPOS_ANUNCIO:
            if anuncio.get(campo) not in (None, ""):
                partes.append(f"{campo}={_limpia_campo(anuncio[campo])}")
        liga = str(anuncio.get("url") or "").strip()
        if liga and url_pagina and not liga.startswith(("http://", "https://")):
            liga = urljoin(url_pagina, liga)
        if liga.startswith(("http://", "https://")):
            partes.append(f"url={liga}")
        clave = "|".join(partes)
        if clave in vistos:
            continue
        vistos.add(clave)
        lineas.append(" | ".join(partes))
        if len(lineas) >= MAX_ANUNCIOS_POR_PAGINA:
            break
    if not lineas:
        return ""
    cuerpo = ""
    for i, linea in enumerate(lineas, 1):
        siguiente = f"{i}) {linea}\n"
        if len(cuerpo) + len(siguiente) > MAX_STRUCT_CHARS:
            break
        cuerpo += siguiente
    total = cuerpo.count("\n")
    return (f"{MARCA_ANUNCIOS} (alta confianza, {total} anuncio"
            f"{'s' if total != 1 else ''}, cada línea es un anuncio distinto con sus propios datos):\n"
            + cuerpo + "\n")


# API v2 de Firecrawl (la actual). Antes se llamaba a /v1/scrape pero con el
# formato JSON de v2 ({"type": "json", ...} dentro de "formats"); v1 sólo
# acepta textos en "formats" y la extracción va en "jsonOptions", así que
# Firecrawl rechazaba TODAS las páginas con 400 Bad Request.
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"


def firecrawl_scrape_payload(url: str) -> Dict[str, Any]:
    """Cuerpo de POST /v2/scrape (docs.firecrawl.dev/api-reference/endpoint/scrape)."""
    formats: List[Dict[str, Any]] = [{"type": "markdown"}]
    if FIRECRAWL_STRUCTURED_EXTRACT:
        # Además del markdown, Firecrawl rellena un esquema fijo
        # (precio/m²/recámaras/baños/estacionamientos) con su propio LLM
        # leyendo la página ya renderizada. Cuesta crédito extra.
        formats.append({
            "type": "json",
            "prompt": _FIRECRAWL_LISTING_PROMPT,
            "schema": _FIRECRAWL_LISTING_SCHEMA,
        })
    return {
        "url": url,
        "formats": formats,
        "onlyMainContent": True,
        "proxy": "auto",                                        # basic | enhanced | auto
        "timeout": max(1000, min(300000, int(FIRECRAWL_TIMEOUT * 1000))),   # milisegundos
        "location": {"country": "MX", "languages": ["es-MX"]},
    }


def firecrawl_search_payload(query: str, pais: str = PAIS_DEFAULT) -> Dict[str, Any]:
    """Cuerpo de POST /v2/search (docs.firecrawl.dev/api-reference/endpoint/search)."""
    return {"query": query[:500], "limit": 8, "sources": ["web"], "country": pais}


def _log_error_firecrawl(operacion: str, url: str, response) -> None:
    """Motivo exacto del rechazo en los logs de Railway (sin la llave: el
    cuerpo de la respuesta de Firecrawl no la incluye)."""
    try:
        cuerpo = (response.text or "")[:300].replace("\n", " ")
    except Exception:
        cuerpo = ""
    if FIRECRAWL_API_KEY:
        cuerpo = cuerpo.replace(FIRECRAWL_API_KEY, "***")
    _log_firecrawl(f"error {operacion} http_{getattr(response, 'status_code', '?')} {url[:120]} — {cuerpo}")


async def _firecrawl_scrape(url: str) -> Dict[str, Any]:
    if not FIRECRAWL_API_KEY:
        return {"ok": False, "error": "no_api_key", "page_text": "", "credits": 0}
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT + 5) as client:
            response = await client.post(FIRECRAWL_SCRAPE_URL, json=firecrawl_scrape_payload(url), headers=headers)
        if response.status_code != 200:
            _log_error_firecrawl("scrape", url, response)
            return {"ok": False, "error": f"http_{response.status_code}", "page_text": "", "credits": 0}
        data_all = response.json() or {}
        if not data_all.get("success"):
            _log_error_firecrawl("scrape", url, response)
            return {
                "ok": False,
                "error": data_all.get("error") or "no_success",
                "page_text": "",
                "credits": 0,
            }
        data = data_all.get("data") or {}
        text = (data.get("markdown") or "")[:MAX_TEXT_CHARS_PER_URL]
        estructurado = data.get("json") or {}
        if isinstance(estructurado, dict):
            linea = _formatea_estructurado_firecrawl(estructurado, url)
            if linea:
                text = linea + text
        meta = data.get("metadata") or {}
        credits = int(meta.get("creditsUsed") or data_all.get("creditsUsed") or 1)
        return {"ok": True, "page_text": text, "credits": credits}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "page_text": "", "credits": 0}


# Versión del formato guardado en caché. Las filas viejas ("ok_firecrawl")
# traen el bloque estructurado de un solo anuncio y el texto recortado más
# corto: no se reutilizan, se vuelven a leer y se sobrescriben.
CACHE_FETCH_STATUS = "ok_firecrawl_v2"


async def _avm_cache_lookup(url: str) -> Optional[str]:
    """Caché durable (Supabase, no en memoria) de páginas ya raspadas por
    Firecrawl. Dos valuaciones en la misma colonia con días de diferencia
    tocan a menudo las mismas URLs de portal — sin esto se le vuelve a
    cobrar crédito a Firecrawl por la misma página cada vez. Si la tabla no
    existe todavía o Supabase no responde, se ignora en silencio (None): la
    caché es solo una optimización de crédito, nunca debe tumbar una
    valuación."""
    canon = _canonical_url(url)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=AVM_CACHE_TTL_DAYS)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                rest_url("avm_scrape_cache"),
                headers=service_headers(),
                params={
                    "url": f"eq.{canon}",
                    "fetch_status": f"eq.{CACHE_FETCH_STATUS}",
                    "creado_en": f"gte.{cutoff}",
                    "select": "page_text",
                    "limit": "1",
                },
            )
        if resp.status_code == 200:
            filas = resp.json() or []
            if filas:
                return filas[0].get("page_text") or None
    except Exception:
        pass
    return None


async def _avm_cache_store(url: str, colonia: str, ciudad: str, page_text: str) -> None:
    if not page_text:
        return
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                rest_url("avm_scrape_cache"),
                headers=service_headers(prefer="resolution=merge-duplicates,return=minimal"),
                json={
                    "url": _canonical_url(url),
                    "host": _host(url),
                    "colonia": colonia or None,
                    "ciudad": ciudad or None,
                    "fetch_status": CACHE_FETCH_STATUS,
                    "page_text": page_text[:MAX_PAGE_TEXT_CHARS],
                    "creado_en": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception:
        pass


# Los montos en dólares son ~18 veces más chicos que en pesos mexicanos y
# los de UF ~40.000 veces más chicos que en pesos chilenos: redondear a
# miles un valor en UF lo destruye. La base se achica según la moneda.
_DIVISOR_REDONDEO = {"USD": 10, "UF": 1000}


# Solo se leen anuncios de portales inmobiliarios. Antes cualquier dominio
# que no estuviera en BLOCKED_FETCH_DOMAINS pasaba, y las búsquedas
# genéricas (sin site:) metían notas de periódico ("México autoriza la
# venta de Movistar…" casaba con "venta" + "México" + "precio") que
# ocupaban lugar de lectura y hasta gastaban crédito de Firecrawl.
DOMINIOS_INMOBILIARIOS = set(PORTAL_HINTS) | PREMIUM_FETCH_DOMAINS | {
    "casasyterrenos.com",
    "mitula.mx",
    "century21mexico.com",
    "remax.com.mx",
    "coldwellbanker.com.mx",
}


def es_dominio_inmobiliario(url: str) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in DOMINIOS_INMOBILIARIOS)


# Inmobiliarias locales (sitios propios fuera de los portales): muchas veces
# son la única oferta publicada de locales/oficinas en ciudades medianas. Se
# aceptan solo si el título o resumen del buscador ya parece un anuncio
# (operación + superficie + precio), y nunca de medios o redes sociales,
# para no volver a meter notas de periódico (ver es_dominio_inmobiliario).
_NO_ANUNCIOS = (
    "elpais.com", "eluniversal.com.mx", "milenio.com", "excelsior.com.mx", "jornada.com.mx",
    "elfinanciero.com.mx", "eleconomista.com.mx", "expansion.mx", "forbes.com.mx", "infobae.com",
    "quadratin.com.mx", "lavozdemichoacan.com.mx", "wikipedia.org", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com", "x.com", "twitter.com", "linkedin.com", "pinterest.com",
    "reddit.com", "google.com", "gob.mx",
)
_NO_ANUNCIO_HOST_RE = re.compile(r"noticia|periodic|diario|news|revista|blog", re.IGNORECASE)
_ANUNCIO_OP_RE = re.compile(r"\b(venta|vendo|renta|rento|arrendamiento|alquiler)\b", re.IGNORECASE)
_ANUNCIO_M2_RE = re.compile(r"\d[\d,\.]*\s?(m2|m²|mts|metros)", re.IGNORECASE)
_ANUNCIO_PRECIO_RE = re.compile(r"\$\s?\d[\d,\.]{2,}|\b\d[\d,\.]{3,}\s?(mxn|pesos)\b", re.IGNORECASE)


def parece_anuncio_inmobiliario(item: Dict[str, Any]) -> bool:
    url = item.get("url", "")
    host = _host(url)
    if not host or _NO_ANUNCIO_HOST_RE.search(host):
        return False
    if any(host == d or host.endswith("." + d) for d in _NO_ANUNCIOS):
        return False
    texto = f"{item.get('title', '')} {item.get('snippet', '')}"
    return bool(_ANUNCIO_OP_RE.search(texto) and _ANUNCIO_M2_RE.search(texto)
                and _ANUNCIO_PRECIO_RE.search(texto))


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _portal_name(url: str) -> str:
    host = _host(url)
    for domain, name in PORTAL_HINTS.items():
        if domain in host:
            return name
    return host or "Fuente web"


def _canonical_url(url: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except Exception:
        return url


def _sameish_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _build_search_queries(req: AvmWebSearchRequest, colonias_vecinas: List[str] = ()) -> List[str]:
    tipo = {
        "terreno": "terreno", "casa": "casa", "departamento": "departamento",
        "local": "local comercial", "oficina": "oficina", "bodega": "bodega"
    }.get(req.tipo_inmueble, req.tipo_inmueble)
    op = "venta" if req.operacion == "venta" else "renta"
    # Ciudad/estado ya no tienen default: si vinieran vacíos (llamada directa
    # a la API sin pasar por el selector del frontend) no metemos comillas
    # vacías a la query — eso ensucia la búsqueda en vez de acotarla.
    lugar = " ".join(f'"{v}"' for v in (req.colonia, req.ciudad) if v)
    # Sin "precio m2": los anuncios casi nunca publican esa frase literal y
    # con las comillas de colonia/ciudad la búsqueda base se quedaba casi
    # sin resultados (sobre todo locales/oficinas en renta).
    base = f'{tipo} en {op} {lugar}'.strip()
    if req.pais == PAIS_DEFAULT:
        # MercadoLibre es de los portales con más oferta fuera de CDMX y
        # antes no tenía búsqueda propia.
        portales = ["inmuebles24.com", "lamudi.com.mx", "propiedades.com", "vivanuncios.com.mx",
                    "inmuebles.mercadolibre.com.mx"]
    else:
        portales = list(datos_pais(req.pais)["portales"])[:4]
    queries = [base] + [f'{tipo} {op} {lugar} site:{d}' for d in portales + ["easybroker.com"]]
    if req.estado:
        queries.append(f'{tipo} {op} {lugar} "{req.estado}"')
    # Búsqueda a nivel ciudad con la superficie del sujeto: trae anuncios
    # de tamaño parecido de zonas cercanas cuando la colonia tiene poca
    # oferta publicada (el modelo decide si son comparables por ubicación).
    superficie = req.m2_terreno if req.tipo_inmueble == "terreno" else (req.m2_construccion or req.m2_terreno)
    if req.incluir_busqueda_ciudad and req.ciudad and superficie and superficie > 0:
        queries.append(f'{tipo} en {op} "{req.ciudad}" {int(round(superficie))} m2')
    # Colonias colindantes reales (descubiertas por geocodificación, no
    # adivinadas por el modelo): una query genérica por cada una para
    # ampliar la búsqueda sin disparar el número de queries tanto como el
    # bloque site: de arriba.
    for vecina in colonias_vecinas[:3]:
        lugar_vecina = " ".join(f'"{v}"' for v in (vecina, req.ciudad) if v)
        if lugar_vecina:
            queries.append(f'{tipo} en {op} {lugar_vecina}')
    return queries


def _offset_latlng(lat: float, lng: float, dx_km: float, dy_km: float):
    """Desplaza un punto lat/lng por (dx_km, dy_km) con una aproximación
    plana — de sobra para el radio de cientos de metros que interesa aquí,
    no hace falta geodesia exacta."""
    dlat = dy_km / 111.0
    dlng = dx_km / (111.0 * math.cos(math.radians(lat)) or 1)
    return lat + dlat, lng + dlng


# 8 puntos a ~0.9km alrededor del centro de la colonia elegida: suficiente
# para caer típicamente en la colonia contigua sin saltarse varias de un
# salto (una colonia urbana normal mide más que eso de lado a lado).
_VECINDAD_OFFSETS_KM = [
    (0.9, 0), (-0.9, 0), (0, 0.9), (0, -0.9),
    (0.65, 0.65), (-0.65, 0.65), (0.65, -0.65), (-0.65, -0.65),
]


async def _colonias_vecinas(lat: float, lng: float, colonia_actual: str) -> List[str]:
    """Descubre los nombres reales de las colonias contiguas a un punto
    geocodificando en reversa varios puntos a su alrededor — en vez de
    depender de que el modelo "recuerde" la geografía de memoria (poco
    confiable y no escala a cualquier ciudad de México). Se cachea 30 días
    por coordenada: la geografía de una colonia no cambia de un día a otro.
    """
    if not GOOGLE_PLACES_KEY or not lat or not lng:
        return []

    cache_key = f"avm_vecinas_{round(lat, 4)}_{round(lng, 4)}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tasks = [
                client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={
                        "latlng": "{:.6f},{:.6f}".format(*_offset_latlng(lat, lng, dx, dy)),
                        "language": "es",
                        "key": GOOGLE_PLACES_KEY,
                    },
                )
                for dx, dy in _VECINDAD_OFFSETS_KM
            ]
            respuestas = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        return []

    vistas = {_normalize_colonia(colonia_actual)}
    encontradas: List[str] = []
    for resp in respuestas:
        if isinstance(resp, Exception) or resp.status_code != 200:
            continue
        try:
            resultados = resp.json().get("results") or []
        except Exception:
            continue
        if not resultados:
            continue
        # El primer resultado de geocodificación inversa es el más
        # específico — el que trae el nombre de colonia/barrio del punto.
        for comp in resultados[0].get("address_components", []):
            if not any(
                t in comp.get("types", [])
                for t in ("neighborhood", "sublocality", "sublocality_level_1")
            ):
                continue
            nombre = comp.get("long_name", "")
            clave = _normalize_colonia(nombre)
            if nombre and clave not in vistas:
                vistas.add(clave)
                encontradas.append(nombre)

    cache_set(cache_key, encontradas, ttl=86400 * 30)
    return encontradas[:6]


async def _search_google_cse(client: httpx.AsyncClient, query: str, pais: str = PAIS_DEFAULT) -> List[Dict[str, Any]]:
    key = legacy_main_settings.google_cse_api_key
    cx = legacy_main_settings.google_cse_id
    if not key or not cx:
        return []
    params = {"key": key, "cx": cx, "q": query, "num": 10}
    if pais != PAIS_DEFAULT:
        params["gl"] = datos_pais(pais)["gl"]
    response = await client.get(
        "https://www.googleapis.com/customsearch/v1",
        params=params,
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("items", []) or []:
        link = item.get("link")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("snippet", ""), "provider": "google_cse",
            })
    return out


async def _search_serpapi(client: httpx.AsyncClient, query: str, pais: str = PAIS_DEFAULT) -> List[Dict[str, Any]]:
    key = legacy_main_settings.serpapi_api_key
    if not key:
        return []
    response = await client.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "api_key": key, "num": 10, "hl": "es", "gl": datos_pais(pais)["gl"]},
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("organic_results", []) or []:
        link = item.get("link")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("snippet", ""), "provider": "serpapi",
            })
    return out


async def _search_brave(client: httpx.AsyncClient, query: str, pais: str = PAIS_DEFAULT) -> List[Dict[str, Any]]:
    key = legacy_main_settings.brave_search_api_key
    if not key:
        return []
    response = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 10, "country": datos_pais(pais)["gl"].upper(), "search_lang": "es"},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    if response.status_code != 200:
        return []
    out = []
    for item in ((response.json().get("web") or {}).get("results") or []):
        link = item.get("url")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("description", ""), "provider": "brave",
            })
    return out


async def _search_tavily(client: httpx.AsyncClient, query: str, pais: str = PAIS_DEFAULT) -> List[Dict[str, Any]]:
    key = legacy_main_settings.tavily_api_key
    if not key:
        return []
    response = await client.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key, "query": query, "search_depth": "basic",
            "max_results": 10, "include_raw_content": False,
        },
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("results", []) or []:
        link = item.get("url")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("content", ""), "provider": "tavily",
            })
    return out


def firecrawl_resultados_web(data: Any) -> List[Dict[str, Any]]:
    """v2 regresa {"web": [...], "news": [...]}; v1 regresaba la lista directa."""
    if isinstance(data, dict):
        data = data.get("web") or []
    return [x for x in (data or []) if isinstance(x, dict)]


async def _search_firecrawl(client: httpx.AsyncClient, query: str, pais: str = PAIS_DEFAULT) -> List[Dict[str, Any]]:
    """Firecrawl como quinto proveedor de búsqueda, pero solo entra como
    respaldo (ver _collect_search_candidates) cuando los cuatro gratuitos no
    devolvieron nada para una query — así no se le cobra crédito de más a
    algo que Google CSE/SerpAPI/Brave/Tavily ya cubren la mayoría de veces."""
    if not FIRECRAWL_API_KEY:
        return []
    try:
        response = await client.post(
            FIRECRAWL_SEARCH_URL,
            json=firecrawl_search_payload(query, pais),
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            _log_error_firecrawl("search", query, response)
            return []
        data_all = response.json() or {}
        if not data_all.get("success"):
            _log_error_firecrawl("search", query, response)
            return []
        out = []
        for item in firecrawl_resultados_web(data_all.get("data")):
            link = item.get("url")
            if link:
                out.append({
                    "title": item.get("title", ""), "url": link,
                    "snippet": item.get("description", ""), "provider": "firecrawl_search",
                })
        return out
    except Exception:
        return []


async def _collect_search_candidates(req: AvmWebSearchRequest, colonias_vecinas: List[str] = ()) -> Dict[str, Any]:
    queries = _build_search_queries(req, colonias_vecinas)
    providers_configured = {
        "google_cse": bool(legacy_main_settings.google_cse_api_key and legacy_main_settings.google_cse_id),
        "serpapi": bool(legacy_main_settings.serpapi_api_key),
        "brave": bool(legacy_main_settings.brave_search_api_key),
        "tavily": bool(legacy_main_settings.tavily_api_key),
        "firecrawl_search": bool(FIRECRAWL_API_KEY),
    }
    if not any(providers_configured.values()):
        print("[avm] falta configurar una API de búsqueda: GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID, "
              "SERPAPI_API_KEY, BRAVE_SEARCH_API_KEY o TAVILY_API_KEY", flush=True)
        raise HTTPException(status_code=500, detail=_MSG_NO_DISPONIBLE)

    results: List[Dict[str, Any]] = []
    seen = set()

    def _agregar(item: Dict[str, Any], query: str) -> bool:
        url = item.get("url", "")
        canon = _canonical_url(url)
        if not url or canon in seen:
            return False
        if not (es_dominio_inmobiliario(url) or parece_anuncio_inmobiliario(item)):
            return False
        item["portal"] = _portal_name(url)
        item["query"] = query
        seen.add(canon)
        results.append(item)
        return True

    # Antes la primera búsqueda (la genérica) juntaba sola los 24 resultados
    # y se cortaba ahí: las búsquedas por portal (site:inmuebles24.com,
    # site:vivanuncios.com.mx, …) nunca corrían. Ahora cada búsqueda aporta
    # su cuota y los resultados se intercalan, para que las páginas que sí
    # se leen (las primeras AVM_MAX_URLS_TO_FETCH) cubran todos los portales.
    cuota = max(3, math.ceil(MAX_SEARCH_RESULTS / max(1, len(queries))))
    proveedores = (_search_google_cse, _search_brave, _search_tavily, _search_serpapi)

    async def _una_query(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
        propios: List[Dict[str, Any]] = []
        vistos = set()
        # Proveedores en orden, y se deja de llamar en cuanto la búsqueda
        # junta su cuota: no se gasta cuota de API de más.
        for buscar in proveedores:
            try:
                lote = await buscar(client, query, req.pais)
            except Exception:
                lote = []
            for item in lote or []:
                canon = _canonical_url(item.get("url", ""))
                if canon and canon not in vistos:
                    vistos.add(canon)
                    propios.append(item)
            if len(propios) >= cuota:
                break
        if not propios:
            propios = await _search_firecrawl(client, query, req.pais)
        return propios[: cuota * 2]

    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
        por_query = await asyncio.gather(*[_una_query(client, q) for q in queries])

    # Intercalado: el 1º de cada búsqueda, luego el 2º de cada una, etc.
    ronda = 0
    while len(results) < MAX_SEARCH_RESULTS and any(ronda < len(lista) for lista in por_query):
        for query, lista in zip(queries, por_query):
            if ronda < len(lista):
                _agregar(dict(lista[ronda]), query)
                if len(results) >= MAX_SEARCH_RESULTS:
                    break
        ronda += 1
    return {"queries": queries, "results": results, "providers_configured": providers_configured}


def _extract_visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "header", "footer", "nav"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            meta_desc = meta.get("content")
        text = soup.get_text(" ", strip=True)
        return _sameish_text(f"{title} {meta_desc} {text}")[:MAX_TEXT_CHARS_PER_URL]
    except Exception:
        return _sameish_text(re.sub(r"<[^>]+>", " ", html or ""))[:MAX_TEXT_CHARS_PER_URL]


_JSON_LD_TIPOS_UTILES = re.compile(r"Product|Offer|RealEstate|Residence|House|Apartment|SingleFamily", re.I)


def _extract_json_ld(html: str) -> List[Dict[str, Any]]:
    """Busca bloques <script type="application/ld+json"> con pinta de anuncio
    (Product/Offer/RealEstateListing de schema.org). La mayoría de portales
    inmobiliarios los usan para SEO — es el mismo precio y superficie que ve
    el usuario, pero en JSON limpio en vez de enterrado en texto de página
    junto con menús, anuncios y "propiedades similares". Leer esto primero
    es mucho más confiable que pedirle al modelo que lo adivine del texto
    plano."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return []

    encontrados: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        bloques = data if isinstance(data, list) else [data]
        for bloque in bloques:
            if not isinstance(bloque, dict):
                continue
            candidatos = bloque.get("@graph") if isinstance(bloque.get("@graph"), list) else [bloque]
            for cand in candidatos:
                if not isinstance(cand, dict):
                    continue
                tipo = cand.get("@type", "")
                tipo_str = " ".join(tipo) if isinstance(tipo, list) else str(tipo)
                if _JSON_LD_TIPOS_UTILES.search(tipo_str):
                    encontrados.append(cand)
    return encontrados[:5]


def _resumen_json_ld(bloques: List[Dict[str, Any]]) -> str:
    """Convierte los bloques JSON-LD encontrados en un resumen corto y
    explícito para el modelo, marcado como dato de alta confianza."""
    partes = []
    for item in bloques:
        oferta = item.get("offers")
        if isinstance(oferta, list):
            oferta = oferta[0] if oferta else {}
        if not isinstance(oferta, dict):
            oferta = {}
        precio = oferta.get("price") or item.get("price")
        moneda = oferta.get("priceCurrency") or item.get("priceCurrency") or "MXN"
        nombre = _sameish_text(str(item.get("name", "")))[:200]
        direccion = item.get("address")
        if isinstance(direccion, dict):
            direccion = ", ".join(str(v) for v in direccion.values() if isinstance(v, (str, int, float)))
        area = item.get("floorSize") or item.get("area")
        if isinstance(area, dict):
            area = area.get("value")

        campos = []
        if nombre:
            campos.append(f"nombre={nombre}")
        if precio:
            campos.append(f"precio={precio} {moneda}")
        if area:
            campos.append(f"superficie={area}")
        if direccion:
            campos.append(f"direccion={_sameish_text(str(direccion))[:200]}")
        if campos:
            partes.append("DATO ESTRUCTURADO JSON-LD (alta confianza): " + "; ".join(campos))
    return "\n".join(partes)


_PRECIO_MXN_RE = re.compile(r"\$\s?[\d][\d,\.]{4,}")


def _advertencia_multi_listado(texto: str) -> str:
    """Si el texto trae muchos precios distintos, probablemente es una
    página de resultados/listado (varias propiedades revueltas) y no el
    detalle de un solo anuncio — el modelo no debería asumir que el primer
    precio que ve corresponde a la superficie del sujeto. Si la página ya
    trae el bloque de anuncios estructurados, cada línea de ese bloque sí es
    un anuncio individual usable (antes la advertencia hacía que se
    descartaran todos)."""
    precios_unicos = set(_PRECIO_MXN_RE.findall(texto or ""))
    if len(precios_unicos) < 5:
        return ""
    if MARCA_ANUNCIOS in (texto or ""):
        return (
            "ADVERTENCIA AUTOMÁTICA: esta página es un listado de resultados "
            "con varias propiedades. Usa cada línea del bloque de anuncios "
            "estructurados como un comparable individual (cada una trae su "
            "propio precio y superficie). No le asignes al inmueble sujeto "
            "precios sueltos del texto libre de abajo que no estén en ese "
            "bloque.\n\n"
        )
    return (
        "ADVERTENCIA AUTOMÁTICA: esta página trae "
        f"{len(precios_unicos)} precios distintos — probablemente es un "
        "listado de resultados con varias propiedades, no el detalle de "
        "un solo anuncio. Solo usa un precio como comparable individual si "
        "el texto deja claro qué superficie (y de preferencia qué ubicación) "
        "le corresponde a ESE precio; cada tarjeta de anuncio con precio y "
        "m² propios cuenta como un comparable distinto. Si esta misma "
        "página trae un indicador agregado del portal (precio promedio/"
        "medio de la zona, rango de precios, número de propiedades "
        "activas), también puedes usar ESE dato como comparable de baja "
        "confianza.\n\n"
    )


_BLOQUEO_RE = re.compile(
    r"verifica que eres human|verificar que no eres un rob|"
    r"i'?m not a robot|are you a human|unusual traffic|"
    r"inicia sesi[oó]n para (ver|continuar)|debes iniciar sesi[oó]n|"
    r"please enable javascript|enable cookies|access denied|"
    r"attention required|checking your browser|"
    r"solicitamos que verifiques|\bcaptcha\b",
    re.IGNORECASE,
)


def _pagina_bloqueada(texto: str) -> bool:
    """Detecta cuando un fetch respondió 200 pero en realidad es un muro de
    captcha, login o verificación anti-bot — no un error HTTP, así que sin
    esto se aceptaba como evidencia "válida" con texto basura en vez de
    reintentarse por Firecrawl (que sí sabe evadir estos muros con proxy
    rotativo). Este era el motivo real detrás de AVMs que terminaban en
    confianza baja pese a tratarse de zonas con oferta real: las páginas
    fetcheadas directo venían bloqueadas, no vacías de mercado."""
    return bool(_BLOQUEO_RE.search(texto or ""))


def _build_page_summary(html: str) -> str:
    """Texto final que se manda al modelo por cada página: primero el dato
    estructurado (si lo hay), luego la advertencia de multi-listado (si
    aplica), y al final el texto visible de respaldo."""
    json_ld = _resumen_json_ld(_extract_json_ld(html))
    visible = _extract_visible_text(html)
    advertencia = _advertencia_multi_listado(visible)
    partes = [p for p in (json_ld, advertencia.strip()) if p]
    resumen = "\n\n".join(partes)
    if resumen:
        return _sameish_text(resumen + "\n\n" + visible)[:MAX_TEXT_CHARS_PER_URL]
    return visible


async def _fetch_candidate_pages(
    candidates: List[Dict[str, Any]], colonia: str = "", ciudad: str = "",
    resumen: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
    }
    sem_http = asyncio.Semaphore(3)
    sem_fc = asyncio.Semaphore(FIRECRAWL_CONCURRENCY)
    stats = {"firecrawl_calls": 0, "firecrawl_credits": 0, "firecrawl_cache_hits": 0,
             "firecrawl_intentos": 0, "firecrawl_errores": {}}

    async def _try_httpx(url: str) -> Dict[str, Any]:
        async with sem_http:
            response = await fetch_public_http_result(
                url,
                timeout=FETCH_TIMEOUT,
                headers=headers,
            )
        ctype = (response.headers.get("content-type") or "").lower()
        if response.status_code >= 400 or "text/html" not in ctype:
            return {"ok": False, "status": response.status_code, "text": ""}
        return {"ok": True, "status": response.status_code, "text": _build_page_summary(response.text)}

    async def _try_firecrawl(url: str) -> Dict[str, Any]:
        cacheado = await _avm_cache_lookup(url)
        if cacheado is not None:
            stats["firecrawl_cache_hits"] += 1
            return {"ok": True, "page_text": cacheado, "credits": 0, "from_cache": True}
        stats["firecrawl_intentos"] += 1
        async with sem_fc:
            result = await _firecrawl_scrape(url)
        if not result.get("ok"):
            err = str(result.get("error") or "error")[:60]
            stats["firecrawl_errores"][err] = stats["firecrawl_errores"].get(err, 0) + 1
        if result.get("ok"):
            stats["firecrawl_calls"] += 1
            stats["firecrawl_credits"] += int(result.get("credits") or 0)
            # Firecrawl entrega markdown, no HTML — no hay JSON-LD que sacar,
            # pero sí vale la pena la misma advertencia de multi-listado.
            advertencia = _advertencia_multi_listado(result.get("page_text", ""))
            if advertencia:
                result["page_text"] = advertencia + result["page_text"]
            await _avm_cache_store(url, colonia, ciudad, result["page_text"])
        return result

    async def one(item: Dict[str, Any]) -> Dict[str, Any]:
        url = item.get("url", "")
        host = _host(url)
        if any(bad in host for bad in BLOCKED_FETCH_DOMAINS):
            return {**item, "fetch_status": "skipped_domain", "page_text": ""}

        is_premium = any(domain in host for domain in PREMIUM_FETCH_DOMAINS)
        try:
            if is_premium and FIRECRAWL_API_KEY:
                firecrawl = await _try_firecrawl(url)
                if firecrawl.get("ok"):
                    return {**item, "fetch_status": "ok_firecrawl", "page_text": firecrawl["page_text"]}
                try:
                    direct = await _try_httpx(url)
                    if direct["ok"] and not _pagina_bloqueada(direct["text"]):
                        return {**item, "fetch_status": "ok_httpx_fallback", "page_text": direct["text"]}
                    motivo = "bloqueada" if direct["ok"] else f"http_{direct.get('status')}"
                    return {
                        **item,
                        "fetch_status": f"firecrawl_{firecrawl.get('error','err')}__{motivo}",
                        "page_text": "",
                    }
                except Exception as exc:
                    return {
                        **item,
                        "fetch_status": f"firecrawl_{firecrawl.get('error','err')}__httpx_err",
                        "fetch_error": str(exc)[:120],
                        "page_text": "",
                    }

            try:
                direct = await _try_httpx(url)
            except Exception as exc:
                # Los muros anti-bot muchas veces no responden 403: cortan la
                # conexión o la dejan colgada hasta el timeout. Antes eso
                # terminaba en "error" sin darle oportunidad a Firecrawl.
                direct = {"ok": False, "status": 0, "text": "", "error": str(exc)[:120]}
            bloqueada = direct["ok"] and _pagina_bloqueada(direct["text"])
            if direct["ok"] and not bloqueada:
                return {**item, "fetch_status": "ok", "page_text": direct["text"]}

            status = direct.get("status") or 0
            # Un 200 que en realidad es captcha/login se trata igual que un
            # 403/429/5xx: se le da a Firecrawl la oportunidad de evadir el
            # muro en vez de aceptar la página bloqueada como si fuera
            # evidencia real (eso era lo que dejaba un AVM entero sin
            # comparables verificables aunque sí hubiera oferta en la zona).
            if FIRECRAWL_API_KEY and (bloqueada or status in (0, 401, 403, 429) or status >= 500):
                firecrawl = await _try_firecrawl(url)
                etiqueta = "bloqueo" if bloqueada else ("sin_respuesta" if status == 0 else str(status))
                if firecrawl.get("ok"):
                    return {
                        **item,
                        "fetch_status": f"ok_firecrawl_retry_{etiqueta}",
                        "page_text": firecrawl["page_text"],
                    }
                return {
                    **item,
                    "fetch_status": f"{'bloqueo' if bloqueada else 'http_' + str(status)}__firecrawl_{firecrawl.get('error','err')}",
                    "page_text": "",
                }
            if bloqueada:
                return {**item, "fetch_status": "bloqueada_sin_firecrawl", "page_text": ""}
            if status == 0:
                return {**item, "fetch_status": "error", "fetch_error": direct.get("error", ""), "page_text": ""}
            return {**item, "fetch_status": f"http_{status}", "page_text": ""}
        except Exception as exc:
            return {**item, "fetch_status": "error", "fetch_error": str(exc)[:120], "page_text": ""}

    tasks = [one(candidate) for candidate in candidates[:MAX_URLS_TO_FETCH]]
    fetched = await asyncio.gather(*tasks) if tasks else []
    info = resumen_firecrawl(fetched, stats)
    if resumen is not None:
        resumen.update(info)
    # Siempre, después de cada avalúo: si no se usó, se dice por qué.
    errores = ", ".join(f"{k}×{v}" for k, v in stats["firecrawl_errores"].items()) or "ninguno"
    linea = (f"calls={stats['firecrawl_calls']} intentos={stats['firecrawl_intentos']} "
             f"credits={stats['firecrawl_credits']} cache_hits={stats['firecrawl_cache_hits']} "
             f"paginas={len(fetched)} errores={errores}")
    if info.get("motivo_no_uso"):
        linea += f" — no se usó porque {info['motivo_no_uso']}"
    _log_firecrawl(linea)
    return fetched


def estado_lectura_simple(fetch_status: str) -> str:
    """Traduce el estado técnico de cada página a lo que ve la persona."""
    st = fetch_status or ""
    if st.startswith("ok_firecrawl"):
        return "leído con Firecrawl"
    if st in ("ok", "ok_httpx_fallback"):
        return "leído"
    if st == "skipped_domain":
        return "omitido"
    return "bloqueado"


def resumen_firecrawl(paginas: List[Dict[str, Any]], stats: Dict[str, Any]) -> Dict[str, Any]:
    conteo = {"leído": 0, "leído con Firecrawl": 0, "bloqueado": 0, "omitido": 0}
    for p in paginas:
        conteo[estado_lectura_simple(p.get("fetch_status", ""))] += 1
    motivo = ""
    if not FIRECRAWL_API_KEY:
        motivo = "falta FIRECRAWL_API_KEY en el servidor"
    elif not stats.get("firecrawl_intentos") and not stats.get("firecrawl_cache_hits"):
        motivo = ("ninguna página era de un portal protegido ni salió bloqueada"
                  if paginas else "la búsqueda no encontró páginas que leer")
    return {
        "activo": bool(FIRECRAWL_API_KEY),
        "intentos": stats.get("firecrawl_intentos", 0),
        "leidas": stats.get("firecrawl_calls", 0),
        "cache": stats.get("firecrawl_cache_hits", 0),
        "creditos": stats.get("firecrawl_credits", 0),
        "errores": dict(stats.get("firecrawl_errores") or {}),
        "conteo": conteo,
        "motivo_no_uso": motivo,
    }


