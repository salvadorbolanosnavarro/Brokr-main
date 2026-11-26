# ──────────────────────────────────────────────────────────────────────────
# routers/acm_datos.py · Broquer — Datos del Análisis Comparativo de Mercado
# ──────────────────────────────────────────────────────────────────────────
# De dónde salen los comparables del ACM y cómo se guardan:
#
#   1. Base propia (mercado_comparables). Cada anuncio que Broquer encuentra
#      se guarda UNA vez (deduplicado entre portales), con su primera y
#      última fecha vista y su historial de precios.
#   2. Investigación en vivo: si la base no tiene suficientes comparables
#      cerca, se reutiliza la búsqueda web + lectura de portales
#      (routers/avm_websearch.py) y TODO lo que encuentra se guarda en la
#      base. Así el ACM funciona desde el primer día y cada búsqueda deja la
#      base más completa para la siguiente.
#   3. Recolección nocturna (fase 4): revisa las zonas donde los asesores
#      hacen ACM, detecta bajas de precio y anuncios retirados.
#   4. Datos de la cuenta (fase 5): inventario propio, Bolsa Broquer y
#      cierres reales con su precio de cierre.
#
# La IA sólo LEE anuncios (cuando el portal no trae el bloque estructurado);
# nunca calcula valores. La matemática está en core/acm_calculo.py.
#
# Depende de: migracion-acm.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Request

from core import acm_calculo as calc
from core import acm_mercado as mercado
from core.cache import cache_get, cache_set
from core.config import settings
from core.database import get_rows, patch_rows, post_rows, upsert_rows
from core.legacy_admin import require_legacy_admin
from core.legacy_main_config import legacy_main_settings
from core.telemetry import _track_anthropic

router = APIRouter(tags=["acm_datos"])
log = logging.getLogger("broquer.acm.datos")

# Vigencia de los datos que se usan como comparables.
DIAS_ACTIVO_VIGENTE = 120      # un "activo" no visto en 4 meses ya no es confiable
DIAS_RETIRADO_UTIL = 540       # retirados/vendidos de hasta 18 meses
# Un anuncio que no aparece en ninguna recolección de su zona durante este
# tiempo (y con al menos MIN_CORRIDAS_RETIRO recolecciones) pasa a retirado.
DIAS_SIN_VER_RETIRADO = 30
MIN_CORRIDAS_RETIRO = 3
MIN_COMPARABLES_SIN_INVESTIGAR = 8
MAX_PAGINAS_IA = 6
_LOTE_HUELLAS = 40


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _texto_filtro(valor: Any, largo: int = 80) -> str:
    """Valor seguro para un filtro de PostgREST (sin comas, paréntesis ni
    comodines que cambien el sentido del filtro)."""
    limpio = "".join(ch for ch in str(valor or "") if ch.isalnum() or ch in " -.'")
    return limpio.strip()[:largo]


def _eq_o_nulo(texto_normalizado: str) -> str:
    return f"eq.{texto_normalizado}" if texto_normalizado else "is.null"


def _in_textos(valores: Iterable[str]) -> str:
    escapados = [str(v).replace("\\", "\\\\").replace('"', '\\"') for v in valores]
    return "in.(" + ",".join(f'"{v}"' for v in escapados) + ")"


# ── Geocodificación de colonias (con caché durable) ────────────────────────

def clave_colonia(colonia: Any, ciudad: Any, pais: Any) -> str:
    return f"{mercado.normalizar(pais or 'MX')}|{mercado.normalizar(ciudad)}|{mercado.normalizar(colonia)}"


async def coordenadas_colonia(colonia: str, ciudad: str, estado: str, pais: str = "MX") -> Optional[Tuple[float, float]]:
    """Centro aproximado de una colonia. Primero la caché en memoria, luego
    la tabla mercado_colonias_geo y al final Google Geocoding (una vez)."""
    if not mercado.normalizar(colonia) and not mercado.normalizar(ciudad):
        return None
    clave = clave_colonia(colonia, ciudad, pais)
    en_memoria = cache_get(f"acm_geo_{clave}")
    if en_memoria is not None:
        return tuple(en_memoria) if en_memoria else None
    try:
        filas = await get_rows("mercado_colonias_geo", {"clave": f"eq.{clave}", "select": "lat,lng", "limit": "1"})
    except httpx.HTTPError:
        filas = []
    if filas:
        lat, lng = mercado.coordenada(filas[0].get("lat"), 90), mercado.coordenada(filas[0].get("lng"), 180)
        punto = (lat, lng) if lat is not None and lng is not None else None
        cache_set(f"acm_geo_{clave}", list(punto) if punto else [], ttl=86400)
        return punto
    if not settings.google_places_key:
        return None
    direccion = ", ".join(p for p in (colonia, ciudad, estado) if p)
    punto = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": direccion, "region": (pais or "MX").lower(), "language": "es",
                        "key": settings.google_places_key},
            )
        resultados = r.json().get("results") or [] if r.status_code == 200 else []
        if resultados:
            loc = resultados[0].get("geometry", {}).get("location", {})
            lat, lng = mercado.coordenada(loc.get("lat"), 90), mercado.coordenada(loc.get("lng"), 180)
            if lat is not None and lng is not None:
                punto = (lat, lng)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("[acm] no se pudo geocodificar %s: %s", direccion, exc)
        return None
    try:
        await upsert_rows("mercado_colonias_geo", {
            "clave": clave, "colonia": colonia or None, "ciudad": ciudad or None, "estado": estado or None,
            "pais": pais or "MX", "lat": punto[0] if punto else None, "lng": punto[1] if punto else None,
        }, conflict="clave", prefer="resolution=merge-duplicates,return=minimal")
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudo guardar la caché de geocodificación: %s", exc)
    cache_set(f"acm_geo_{clave}", list(punto) if punto else [], ttl=86400)
    return punto


# ── Guardar anuncios en la base propia ─────────────────────────────────────

async def _ubicar(comps: List[Dict[str, Any]]) -> None:
    """Coordenadas de colonia para los anuncios que no traen las suyas."""
    pendientes: Dict[str, Dict[str, Any]] = {}
    for c in comps:
        if c.get("lat") is None and (c.get("colonia") or c.get("ciudad")):
            pendientes.setdefault(clave_colonia(c.get("colonia"), c.get("ciudad"), c.get("pais")), c)
    claves = list(pendientes)
    puntos = await asyncio.gather(*[
        coordenadas_colonia(pendientes[k].get("colonia") or "", pendientes[k].get("ciudad") or "",
                            pendientes[k].get("estado") or "", pendientes[k].get("pais") or "MX")
        for k in claves
    ])
    por_clave = dict(zip(claves, puntos))
    for c in comps:
        if c.get("lat") is None:
            punto = por_clave.get(clave_colonia(c.get("colonia"), c.get("ciudad"), c.get("pais")))
            if punto:
                c["lat"], c["lng"] = punto
                c["precision_ubicacion"] = "colonia" if c.get("colonia") else "ciudad"


async def guardar_comparables(nuevos: List[Dict[str, Any]], *, ahora: Optional[datetime] = None) -> Dict[str, int]:
    """Inserta anuncios nuevos y actualiza los ya conocidos (última vez visto,
    cambios de precio). Devuelve conteos {nuevos, actualizados, bajas}."""
    ahora = ahora or _ahora()
    utiles: Dict[str, Dict[str, Any]] = {}
    for c in nuevos:
        if not mercado.es_util(c):
            continue
        utiles.setdefault(mercado.huella_comparable(c), c)
    if not utiles:
        return {"nuevos": 0, "actualizados": 0, "bajas": 0}
    lista = list(utiles.values())
    await _ubicar(lista)

    candidatas = sorted({h for c in lista for h in mercado.huellas_candidatas(c)})
    existentes: List[Dict[str, Any]] = []
    for i in range(0, len(candidatas), _LOTE_HUELLAS):
        lote = candidatas[i:i + _LOTE_HUELLAS]
        existentes += await get_rows("mercado_comparables", {
            "huella": _in_textos(lote),
            "select": "id,huella,precio,veces_visto,bajas_precio,url,foto_url,lat,lng,estatus",
        })

    conteo = {"nuevos": 0, "actualizados": 0, "bajas": 0}
    usados: set = set()
    for c in lista:
        fila = mercado.elegir_existente(c, (e for e in existentes if e["id"] not in usados))
        precio = mercado.numero(c["precio"])
        if fila:
            usados.add(fila["id"])
            cambios: Dict[str, Any] = {
                "ultima_vez": _iso(ahora), "actualizado_en": _iso(ahora),
                "veces_visto": int(fila.get("veces_visto") or 0) + 1,
                "estatus": "activo", "retirado_en": None,
            }
            anterior = mercado.numero(fila.get("precio")) or precio
            if abs(precio - anterior) / anterior > 0.005:
                cambios["precio"] = precio
                if precio < anterior:
                    cambios["bajas_precio"] = int(fila.get("bajas_precio") or 0) + 1
                    conteo["bajas"] += 1
                await post_rows("mercado_precios_historial",
                                {"comparable_id": fila["id"], "precio": precio, "moneda": c.get("moneda") or "MXN"},
                                prefer="return=minimal")
            for campo in ("url", "foto_url"):
                if c.get(campo) and not fila.get(campo):
                    cambios[campo] = c[campo]
            if fila.get("lat") is None and c.get("lat") is not None:
                cambios.update({"lat": c["lat"], "lng": c["lng"], "precision_ubicacion": c.get("precision_ubicacion") or "colonia"})
            await patch_rows("mercado_comparables", {"id": f"eq.{fila['id']}"}, cambios)
            conteo["actualizados"] += 1
            continue
        registro = {
            "huella": mercado.huella_comparable(c),
            "fuente": c.get("fuente") or "portal",
            "portal": c.get("portal"), "url": c.get("url"), "titulo": c.get("titulo"),
            "tipo": c["tipo"], "operacion": c["operacion"],
            "precio": precio, "precio_inicial": precio, "moneda": c.get("moneda") or "MXN",
            "m2_construccion": c.get("m2_construccion"), "m2_terreno": c.get("m2_terreno"),
            "recamaras": c.get("recamaras"), "banos": c.get("banos"),
            "estacionamientos": c.get("estacionamientos"), "antiguedad": c.get("antiguedad"),
            "colonia": c.get("colonia"), "colonia_norm": mercado.normalizar(c.get("colonia")) or None,
            "ciudad": c.get("ciudad"), "ciudad_norm": mercado.normalizar(c.get("ciudad")) or None,
            "estado": c.get("estado"), "pais": c.get("pais") or "MX",
            "lat": c.get("lat"), "lng": c.get("lng"),
            "precision_ubicacion": c.get("precision_ubicacion") or "colonia",
            "foto_url": c.get("foto_url"),
            "primera_vez": _iso(ahora), "ultima_vez": _iso(ahora), "veces_visto": 1,
        }
        try:
            creada = await post_rows("mercado_comparables", registro)
        except httpx.HTTPStatusError as exc:
            # Otra búsqueda simultánea lo insertó primero (huella única).
            log.info("[acm] anuncio ya existente al insertar: %s", exc.response.status_code)
            continue
        if creada:
            await post_rows("mercado_precios_historial",
                            {"comparable_id": creada[0]["id"], "precio": precio, "moneda": registro["moneda"]},
                            prefer="return=minimal")
        conteo["nuevos"] += 1
    return conteo


# ── Consultar la base propia ───────────────────────────────────────────────

def _fila_a_comparable(f: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"m-{f['id']}", "origen": "mercado",
        "titulo": f.get("titulo"), "url": f.get("url"), "portal": f.get("portal"), "foto_url": f.get("foto_url"),
        "tipo": f.get("tipo"), "operacion": f.get("operacion"),
        "precio": mercado.numero(f.get("precio")), "precio_inicial": mercado.numero(f.get("precio_inicial")),
        "moneda": f.get("moneda") or "MXN",
        "m2_construccion": mercado.numero(f.get("m2_construccion")), "m2_terreno": mercado.numero(f.get("m2_terreno")),
        "recamaras": f.get("recamaras"), "banos": mercado.numero(f.get("banos")),
        "estacionamientos": f.get("estacionamientos"), "antiguedad": f.get("antiguedad"),
        "colonia": f.get("colonia"), "ciudad": f.get("ciudad"),
        "lat": mercado.coordenada(f.get("lat"), 90), "lng": mercado.coordenada(f.get("lng"), 180),
        "precision_ubicacion": f.get("precision_ubicacion") or "colonia",
        "primera_vez": f.get("primera_vez"), "ultima_vez": f.get("ultima_vez"),
        "estatus": f.get("estatus") or "activo", "retirado_en": f.get("retirado_en"),
        "bajas_precio": f.get("bajas_precio") or 0,
    }


async def comparables_de_mercado(sujeto: Dict[str, Any], *, ahora: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Comparables de la base propia alrededor del sujeto. Amplía el radio
    (700 m → 6 km) hasta juntar suficientes compatibles."""
    ahora = ahora or _ahora()
    base = {
        "pais": f"eq.{_texto_filtro(sujeto.get('pais') or 'MX', 3)}",
        "operacion": f"eq.{sujeto['operacion']}",
        "tipo": f"eq.{sujeto['tipo']}",
        "or": (f"(and(estatus.eq.activo,ultima_vez.gte.{_iso(ahora - timedelta(days=DIAS_ACTIVO_VIGENTE))}),"
               f"and(estatus.eq.retirado,retirado_en.gte.{_iso(ahora - timedelta(days=DIAS_RETIRADO_UTIL))}))"),
        "select": "*",
        "limit": "400",
    }
    lat, lng = sujeto.get("lat"), sujeto.get("lng")
    if lat is None or lng is None:
        filas = await get_rows("mercado_comparables", {
            **base,
            "ciudad_norm": _eq_o_nulo(mercado.normalizar(sujeto.get("ciudad"))),
            "colonia_norm": _eq_o_nulo(mercado.normalizar(sujeto.get("colonia"))),
        })
        return [_fila_a_comparable(f) for f in filas]
    filas: List[Dict[str, Any]] = []
    for radio in calc.RADIOS_BUSQUEDA_M:
        a, b, c, d = calc.caja(lat, lng, radio)
        filas = await get_rows("mercado_comparables", {**base, "and": f"(lat.gte.{a},lat.lte.{b},lng.gte.{c},lng.lte.{d})"})
        compatibles = [f for f in filas if calc.compatible(sujeto, _fila_a_comparable(f))]
        if len(compatibles) >= calc.MIN_COMPARABLES_RADIO:
            break
    return [_fila_a_comparable(f) for f in filas]


# ── Datos de la cuenta: inventario, bolsa y cierres ────────────────────────

_CAMPOS_PROPIEDAD = ("id,titulo,tipo,subtipo,operacion,estatus,precio,moneda,colonia,ciudad,estado,"
                     "m2_construccion,m2_terreno,recamaras,banos,estacionamientos,antiguedad,lat,lng,fotos,"
                     "publicada_en,created_at,org_id,user_id")


def _filtro_ciudad(sujeto: Dict[str, Any]) -> Dict[str, str]:
    ciudad = _texto_filtro(sujeto.get("ciudad"))
    return {"ciudad": f"ilike.*{ciudad}*"} if ciudad else {}


async def comparables_de_cuenta(ctx: Dict[str, Any], sujeto: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Inventario activo de la cuenta y Bolsa Broquer en la misma ciudad."""
    if not sujeto.get("ciudad"):
        return []
    filtro_op = "like.renta*" if sujeto["operacion"] == "renta" else "eq.venta"
    comunes = {"tipo": f"eq.{sujeto['tipo']}", "operacion": filtro_op, "estatus": "eq.activa",
               "precio": "gt.0", "select": _CAMPOS_PROPIEDAD, "limit": "150", **_filtro_ciudad(sujeto)}
    salida: List[Dict[str, Any]] = []
    try:
        dueno = {"org_id": f"eq.{ctx['org_id']}"} if ctx.get("org_id") else {"user_id": f"eq.{ctx['user_id']}"}
        propias = await get_rows("propiedades", {**comunes, **dueno})
        bolsa = await get_rows("propiedades", {**comunes, "en_bolsa": "eq.true"})
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudo leer inventario/bolsa: %s", exc)
        return []
    propias_ids = {p["id"] for p in propias}
    for p in propias:
        if p["id"] == sujeto.get("propiedad_id"):
            continue
        c = mercado.comparable_desde_propiedad(p, origen="inventario")
        if c:
            salida.append(c)
    for p in bolsa:
        if p["id"] in propias_ids or p["id"] == sujeto.get("propiedad_id"):
            continue
        c = mercado.comparable_desde_propiedad(p, origen="bolsa")
        if c:
            salida.append(c)
    return salida


async def cierres_de_cuenta(ctx: Dict[str, Any], *, dias: int = 730) -> List[Dict[str, Any]]:
    """Cierres reales de la cuenta (últimos 2 años) con el inmueble ligado."""
    if not ctx.get("org_id"):
        return []
    desde = (_ahora() - timedelta(days=dias)).date().isoformat()
    try:
        cierres = await get_rows("cierres", {
            "org_id": f"eq.{ctx['org_id']}", "etapa": "eq.cerrada", "fecha_cierre": f"gte.{desde}",
            "select": "id,propiedad_id,tipo_operacion,fecha_cierre,precio_cierre,moneda_cierre,precio_publicacion,publicada_en",
            "limit": "500",
        })
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudo leer cierres: %s", exc)
        return []
    ids = sorted({c["propiedad_id"] for c in cierres if c.get("propiedad_id")})
    props: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(ids), 80):
        try:
            for p in await get_rows("propiedades", {"id": f"in.({','.join(ids[i:i + 80])})", "select": _CAMPOS_PROPIEDAD}):
                props[p["id"]] = p
        except httpx.HTTPError:
            continue
    for c in cierres:
        c["propiedad"] = props.get(c.get("propiedad_id"))
    return cierres


def comparables_de_cierres(cierres: List[Dict[str, Any]], sujeto: Dict[str, Any]) -> List[Dict[str, Any]]:
    salida = []
    for ci in cierres:
        p = ci.get("propiedad")
        precio = mercado.numero(ci.get("precio_cierre"))
        if not p or not precio or p.get("id") == sujeto.get("propiedad_id"):
            continue
        if mercado.normalizar(sujeto.get("ciudad")) not in mercado.normalizar(p.get("ciudad")):
            continue
        c = mercado.comparable_desde_propiedad({**p, "precio": precio, "moneda": ci.get("moneda_cierre") or p.get("moneda")},
                                               origen="cierre")
        if not c:
            continue
        c.update({
            "id": f"cierre-{ci['id']}", "portal": "Cierre de la cuenta",
            "operacion": "renta" if str(ci.get("tipo_operacion") or "").startswith("renta") else "venta",
            "precio_cierre": precio, "precio_publicacion": mercado.numero(ci.get("precio_publicacion")),
            "fecha_cierre": ci.get("fecha_cierre"), "publicada_en": ci.get("publicada_en") or p.get("publicada_en"),
            "estatus": "retirado",
        })
        salida.append(c)
    return salida


# ── Investigación en vivo (reutiliza la búsqueda del AVM) ──────────────────

_PROMPT_EXTRAER = """Eres un extractor de datos de anuncios inmobiliarios. Recibes el texto visible de varias páginas públicas de portales.
Devuelve SOLO los anuncios individuales que aparezcan con precio. No calcules valores, no estimes, no inventes: si un dato no aparece explícitamente para ESE anuncio, omítelo. Nunca mezcles datos de anuncios distintos. No incluyas teléfonos, nombres ni datos personales.

Responde ÚNICAMENTE JSON válido:
{"anuncios":[{"pagina":1,"titulo":"","ubicacion":"","tipo":"casa|departamento|terreno|local|oficina|bodega|otro","operacion":"venta|renta","precio":0,"moneda":"MXN","m2_construccion":0,"m2_terreno":0,"recamaras":0,"banos":0,"estacionamientos":0,"antiguedad":0,"url":""}]}"""


async def _extraer_con_ia(paginas: List[Dict[str, Any]], user_id: Optional[str]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Para páginas sin bloque estructurado: la IA sólo transcribe anuncios."""
    if not paginas or not settings.anthropic_api_key:
        return []
    evidencia = [{"pagina": i + 1, "url": p.get("url", ""), "texto": (p.get("page_text") or "")[:7000]}
                 for i, p in enumerate(paginas)]
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{settings.anthropic_base}/messages",
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": legacy_main_settings.anthropic_avm_model, "max_tokens": 8000, "temperature": 0,
                      "system": _PROMPT_EXTRAER,
                      "messages": [{"role": "user", "content": json.dumps(evidencia, ensure_ascii=False)}]},
            )
    except httpx.HTTPError as exc:
        log.warning("[acm] extracción con IA falló: %s", exc)
        return []
    if r.status_code != 200:
        log.warning("[acm] extracción con IA http_%s", r.status_code)
        return []
    datos = r.json()
    _track_anthropic(user_id, "acm", "/acm/investigar", datos, modelo=datos.get("model") or legacy_main_settings.anthropic_avm_model)
    texto = "".join(b.get("text", "") for b in datos.get("content") or [] if b.get("type") == "text")
    inicio, fin = texto.find("{"), texto.rfind("}")
    try:
        anuncios = json.loads(texto[inicio:fin + 1]).get("anuncios") or [] if inicio >= 0 else []
    except ValueError:
        return []
    salida = []
    for a in anuncios:
        if not isinstance(a, dict):
            continue
        try:
            pagina = paginas[int(a.get("pagina") or 1) - 1]
        except (ValueError, IndexError):
            continue
        salida.append((a, pagina))
    return salida


def _zona_de(sujeto: Dict[str, Any]) -> Dict[str, Any]:
    return {k: sujeto.get(k) for k in ("colonia", "ciudad", "estado", "pais", "tipo", "operacion")}


async def investigar_en_vivo(sujeto: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """Busca anuncios en portales para la zona del sujeto y los GUARDA en la
    base propia. Devuelve conteos; los comparables se leen después de la base."""
    from routers import avm_websearch as avm  # búsqueda y lectura de portales

    zona = _zona_de(sujeto)
    req = avm.AvmWebSearchRequest(
        colonia=sujeto.get("colonia") or sujeto.get("ciudad") or "",
        tipo_inmueble=sujeto["tipo"], operacion=sujeto["operacion"],
        m2_construccion=mercado.numero(sujeto.get("m2_construccion")) or 0,
        m2_terreno=mercado.numero(sujeto.get("m2_terreno")) or 0,
        recamaras=mercado.entero(sujeto.get("recamaras")) or 0,
        ciudad=sujeto.get("ciudad") or "", estado=sujeto.get("estado") or "",
        latitud=sujeto.get("lat") or 0, longitud=sujeto.get("lng") or 0,
        pais=sujeto.get("pais") or "MX",
    )
    try:
        vecinas = await avm._colonias_vecinas(req.latitud, req.longitud, req.colonia)
        busqueda = await avm._collect_search_candidates(req, vecinas)
    except HTTPException as exc:
        log.warning("[acm] búsqueda en vivo no disponible: %s", exc.detail)
        return {"ok": False, "motivo": "busqueda_no_disponible", "nuevos": 0, "actualizados": 0, "bajas": 0}
    if not busqueda.get("results"):
        return {"ok": True, "nuevos": 0, "actualizados": 0, "bajas": 0, "paginas": 0}
    paginas = await avm._fetch_candidate_pages(busqueda["results"], colonia=req.colonia, ciudad=req.ciudad, resumen={})

    anuncios: List[Dict[str, Any]] = []
    sin_estructura: List[Dict[str, Any]] = []
    moneda = "MXN"
    try:
        from core.paises import datos_pais
        moneda = datos_pais(req.pais).get("moneda_avm") or "MXN"
    except Exception:  # pragma: no cover
        pass
    for p in paginas:
        texto = p.get("page_text") or ""
        estructurados = mercado.parse_anuncios_estructurados(texto)
        if estructurados:
            for a in estructurados:
                c = mercado.comparable_desde_anuncio(a, url_pagina=p.get("url", ""), portal=p.get("portal", ""),
                                                     zona=zona, moneda_defecto=moneda)
                if c:
                    anuncios.append(c)
        elif len(texto) > 400:
            sin_estructura.append(p)
    for a, pagina in await _extraer_con_ia(sin_estructura[:MAX_PAGINAS_IA], user_id):
        c = mercado.comparable_desde_anuncio(a, url_pagina=pagina.get("url", ""), portal=pagina.get("portal", ""),
                                             zona=zona, moneda_defecto=moneda)
        if c:
            anuncios.append(c)
    try:
        conteo = await guardar_comparables(anuncios)
    except httpx.HTTPError as exc:
        log.error("[acm] no se pudieron guardar los comparables: %s", exc)
        return {"ok": False, "motivo": "no_se_guardo", "nuevos": 0, "actualizados": 0, "bajas": 0}
    log.info("[acm] investigación %s/%s: %d páginas, %d anuncios, %s",
             sujeto.get("colonia"), sujeto.get("ciudad"), len(paginas), len(anuncios), conteo)
    return {"ok": True, "paginas": len(paginas), "anuncios": len(anuncios), **conteo}


# ── Zonas que se recolectan cada noche ─────────────────────────────────────

def clave_zona(sujeto: Dict[str, Any]) -> str:
    return "|".join([clave_colonia(sujeto.get("colonia"), sujeto.get("ciudad"), sujeto.get("pais")),
                     sujeto.get("tipo") or "", sujeto.get("operacion") or ""])


async def registrar_zona(sujeto: Dict[str, Any]) -> None:
    """Cada ACM le dice a la recolección nocturna dónde trabajan los asesores."""
    if not sujeto.get("ciudad"):
        return
    try:
        await upsert_rows("mercado_zonas", {
            "clave": clave_zona(sujeto), "pais": sujeto.get("pais") or "MX",
            "colonia": sujeto.get("colonia"), "ciudad": sujeto.get("ciudad"), "estado": sujeto.get("estado"),
            "tipo": sujeto["tipo"], "operacion": sujeto["operacion"],
            "lat": sujeto.get("lat"), "lng": sujeto.get("lng"),
            "solicitada_en": _iso(_ahora()),
        }, conflict="clave", prefer="resolution=merge-duplicates,return=minimal")
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudo registrar la zona: %s", exc)


async def marcar_retirados(zona: Dict[str, Any], *, ahora: Optional[datetime] = None) -> int:
    """Tras recolectar una zona varias veces: los anuncios que dejaron de
    aparecer hace más de DIAS_SIN_VER_RETIRADO pasan a 'retirado' (fecha de
    retiro = última vez que se vieron)."""
    ahora = ahora or _ahora()
    if int(zona.get("corridas") or 0) < MIN_CORRIDAS_RETIRO:
        return 0
    limite = _iso(ahora - timedelta(days=DIAS_SIN_VER_RETIRADO))
    filtros = {
        "pais": f"eq.{zona.get('pais') or 'MX'}",
        "ciudad_norm": _eq_o_nulo(mercado.normalizar(zona.get("ciudad"))),
        "colonia_norm": _eq_o_nulo(mercado.normalizar(zona.get("colonia"))),
        "tipo": f"eq.{zona['tipo']}", "operacion": f"eq.{zona['operacion']}",
        "estatus": "eq.activo", "ultima_vez": f"lt.{limite}",
        "select": "id,ultima_vez", "limit": "300",
    }
    filas = await get_rows("mercado_comparables", filtros)
    for f in filas:
        await patch_rows("mercado_comparables", {"id": f"eq.{f['id']}"},
                         {"estatus": "retirado", "retirado_en": f.get("ultima_vez"), "actualizado_en": _iso(ahora)})
    return len(filas)


async def recolectar_zona(zona: Dict[str, Any]) -> Dict[str, Any]:
    sujeto = {k: zona.get(k) for k in ("colonia", "ciudad", "estado", "pais", "tipo", "operacion")}
    sujeto["lat"], sujeto["lng"] = zona.get("lat"), zona.get("lng")
    resultado = await investigar_en_vivo(sujeto)
    corridas = int(zona.get("corridas") or 0) + (1 if resultado.get("ok") else 0)
    retirados = 0
    if resultado.get("ok"):
        retirados = await marcar_retirados({**zona, "corridas": corridas})
    await patch_rows("mercado_zonas", {"clave": f"eq.{zona['clave']}"}, {
        "ultima_recoleccion": _iso(_ahora()), "corridas": corridas,
        "ultimo_resultado": int(resultado.get("anuncios") or 0),
    })
    return {**resultado, "retirados": retirados}


async def zonas_pendientes(limite: int = 25) -> List[Dict[str, Any]]:
    """Zonas pedidas en los últimos 90 días que no se recolectan hace 20 h,
    las más recientes primero."""
    ahora = _ahora()
    return await get_rows("mercado_zonas", {
        "solicitada_en": f"gte.{_iso(ahora - timedelta(days=90))}",
        "or": f"(ultima_recoleccion.is.null,ultima_recoleccion.lt.{_iso(ahora - timedelta(hours=20))})",
        "order": "solicitada_en.desc", "limit": str(limite), "select": "*",
    })


async def recolectar_pendientes(limite: int = 25) -> Dict[str, Any]:
    try:
        zonas = await zonas_pendientes(limite)
    except httpx.HTTPError as exc:
        log.warning("[acm] no se pudieron leer las zonas pendientes: %s", exc)
        return {"zonas": 0}
    total = {"zonas": 0, "nuevos": 0, "actualizados": 0, "bajas": 0, "retirados": 0}
    for zona in zonas:
        try:
            r = await recolectar_zona(zona)
        except Exception as exc:  # una zona fallida no detiene a las demás
            log.warning("[acm] falló la recolección de %s: %s", zona.get("clave"), exc)
            continue
        total["zonas"] += 1
        for k in ("nuevos", "actualizados", "bajas", "retirados"):
            total[k] += int(r.get(k) or 0)
    log.info("[acm] recolección nocturna: %s", total)
    return total


def _hora_local() -> int:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(settings.wa2_zone_default or "America/Mexico_City")).hour
    except Exception:  # pragma: no cover
        return (datetime.now(timezone.utc) - timedelta(hours=6)).hour


async def _ciclo_recoleccion() -> None:
    """Revisa cada hora; sólo trabaja en la ventana nocturna configurada.
    zonas_pendientes() ya evita recolectar la misma zona dos veces el mismo día."""
    while True:
        try:
            if _hora_local() == settings.acm_recoleccion_hora:
                await recolectar_pendientes()
        except Exception as exc:
            log.error("[acm] falló el ciclo de recolección: %s", exc)
        await asyncio.sleep(3600)


@router.on_event("startup")
async def _iniciar_recoleccion() -> None:
    # Gasta crédito de búsqueda, Firecrawl e IA: apagado salvo que se encienda
    # explícitamente, y en UNA sola instancia (igual que el Buscador).
    if not settings.acm_recoleccion_enabled:
        log.warning("Recolección nocturna del ACM DESACTIVADA (ACM_RECOLECCION_ACTIVA); "
                    "el ACM sigue funcionando con búsqueda en vivo.")
        return
    asyncio.create_task(_ciclo_recoleccion())


@router.post("/acm/admin/recolectar")
async def recolectar_ahora(request: Request):
    """Corre la recolección de inmediato (sólo administradores de Broquer)."""
    await require_legacy_admin(request)
    return await recolectar_pendientes()
