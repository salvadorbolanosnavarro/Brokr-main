# ──────────────────────────────────────────────────────────────────────────
# routers/buscador_propiedades.py · Broquer — Buscador de propiedades
# ──────────────────────────────────────────────────────────────────────────
# Cada cliente puede tener un "requerimiento" de búsqueda (operación, tipo
# de inmueble, colonia/ciudad/estado, rango de precio, recámaras mínimas).
# Un ciclo de fondo lo revisa una vez al día (por si el requerimiento
# cambió) y deja listos los enlaces de anuncios que se le parecen, para que
# el usuario los consulte en tiempo real en el portal de origen — Broquer
# no guarda ni muestra el contacto de nadie más, solo el enlace.
#
# Reusa a propósito los proveedores de búsqueda y el scrape estructurado de
# Firecrawl ya construidos en avm_websearch.py (incluida su caché
# avm_scrape_cache) en vez de duplicarlos — es exactamente el mismo tipo de
# búsqueda, solo que aquí el objetivo es encontrar enlaces que calcen con un
# requerimiento, no valuar un inmueble.
#
# Depende de: migracion-buscador-propiedades.sql ya corrido.
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, upsert_rows
from routers import avm_websearch as avm

router = APIRouter(tags=["buscador_propiedades"])
log = logging.getLogger("broquer.buscador")

# Cuántos candidatos se recolectan como máximo por requerimiento y cuántos
# de ellos se verifican de verdad con Firecrawl (crédito real) por corrida.
# La caché compartida con el AVM hace que verificar la misma URL en días
# consecutivos no vuelva a costar crédito.
MAX_CANDIDATOS = 20
MAX_VERIFICAR_PRECIO = 8
MAX_RESULTADOS_GUARDADOS = 15

_RE_PRECIO_ESTRUCTURADO = re.compile(r"DATO ESTRUCTURADO FIRECRAWL[^\n]*?precio=([\d.]+)")


def _require_db() -> None:
    try:
        settings.require_supabase_service()
    except RuntimeError as exc:
        raise HTTPException(500, "Supabase no está configurado en el servidor.") from exc


async def _verificar_contacto(contacto_id: str, uid: str) -> Dict[str, Any]:
    filas = await get_rows("contactos", {
        "id": f"eq.{contacto_id}", "user_id": f"eq.{uid}",
        "select": "id,nombre,es_potencial",
        "limit": "1",
    })
    if not filas:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    return filas[0]


# ── Construcción de queries y extracción de precio ─────────────────────────

_TIPO_LABELS = {
    "terreno": "terreno", "casa": "casa", "departamento": "departamento",
    "local": "local comercial", "oficina": "oficina", "bodega": "bodega",
}

_PORTALES_SITE = (
    "inmuebles24.com", "lamudi.com.mx", "propiedades.com",
    "vivanuncios.com.mx", "easybroker.com",
)


def _construir_queries(req: Dict[str, Any]) -> List[str]:
    tipo = _TIPO_LABELS.get(req.get("tipo_inmueble") or "", req.get("tipo_inmueble") or "casa")
    op = "venta" if (req.get("operacion") or "venta") == "venta" else "renta"
    lugar = " ".join(f'"{v}"' for v in (req.get("colonia"), req.get("ciudad")) if v)

    rango = ""
    precio_min, precio_max = req.get("precio_min"), req.get("precio_max")
    if precio_min and precio_max:
        rango = f" entre {int(precio_min):,} y {int(precio_max):,}"
    elif precio_max:
        rango = f" hasta {int(precio_max):,}"
    elif precio_min:
        rango = f" desde {int(precio_min):,}"

    base = f"{tipo} en {op} {lugar}{rango}".strip()
    queries = [base]
    for dominio in _PORTALES_SITE:
        queries.append(f"{tipo} {op} {lugar} site:{dominio}")
    if req.get("estado"):
        queries.append(f'{tipo} {op} {lugar} "{req["estado"]}"')
    return queries


def _extraer_precio(texto: str) -> Optional[float]:
    m = _RE_PRECIO_ESTRUCTURADO.search(texto or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


async def _recolectar_candidatos(req: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Igual que _collect_search_candidates del AVM (misma lógica de
    respaldo: Firecrawl entra solo cuando los 4 proveedores gratuitos no
    devolvieron nada para una query), pero sin campos de valuación —
    aquí solo interesan enlaces y snippets, no leer cada página completa."""
    queries = _construir_queries(req)
    candidatos: List[Dict[str, Any]] = []
    seen = set()

    def _agregar(item: Dict[str, Any]) -> None:
        url = item.get("url", "")
        canon = avm._canonical_url(url)
        if not url or canon in seen:
            return
        host = avm._host(url)
        if any(bad in host for bad in avm.BLOCKED_FETCH_DOMAINS):
            return
        item["portal"] = avm._portal_name(url)
        seen.add(canon)
        candidatos.append(item)

    async with httpx.AsyncClient(timeout=18, follow_redirects=True) as client:
        for query in queries:
            if len(candidatos) >= MAX_CANDIDATOS:
                break
            batches = await asyncio.gather(
                avm._search_google_cse(client, query),
                avm._search_serpapi(client, query),
                avm._search_brave(client, query),
                avm._search_tavily(client, query),
                return_exceptions=True,
            )
            antes = len(candidatos)
            for batch in batches:
                if isinstance(batch, Exception):
                    continue
                for item in batch:
                    _agregar(item)
            if len(candidatos) == antes:
                for item in await avm._search_firecrawl(client, query):
                    _agregar(item)
    return candidatos[:MAX_CANDIDATOS]


async def _verificar_precio(url: str, req: Dict[str, Any]) -> tuple[Optional[float], bool]:
    """Reusa la caché durable del AVM (avm_scrape_cache): la misma URL
    verificada ayer para otro cliente en la misma colonia no le cuesta
    crédito de nuevo a Firecrawl hoy."""
    cacheado = await avm._avm_cache_lookup(url)
    texto = cacheado
    if texto is None:
        if not avm.FIRECRAWL_API_KEY:
            return None, False
        try:
            resultado = await avm._firecrawl_scrape(url)
        except Exception:
            return None, False
        if not resultado.get("ok"):
            return None, False
        texto = resultado["page_text"]
        await avm._avm_cache_store(url, req.get("colonia") or "", req.get("ciudad") or "", texto)
    precio = _extraer_precio(texto)
    return precio, precio is not None


def _dentro_de_rango(precio: float, req: Dict[str, Any]) -> bool:
    # 10% de tolerancia: esto es un buscador de descubrimiento, no la
    # valuación estricta del AVM — un anuncio justo en el borde del rango
    # sigue siendo relevante para el agente.
    precio_min, precio_max = req.get("precio_min"), req.get("precio_max")
    if precio_min and precio < float(precio_min) * 0.9:
        return False
    if precio_max and precio > float(precio_max) * 1.1:
        return False
    return True


async def _escanear_requerimiento(req: Dict[str, Any]) -> int:
    """Corre una búsqueda para un requerimiento y reemplaza por completo
    sus resultados guardados. Devuelve cuántos quedaron."""
    candidatos = await _recolectar_candidatos(req)

    resultados: List[Dict[str, Any]] = []
    verificados = 0
    for item in candidatos:
        url = item.get("url", "")
        host = avm._host(url)
        es_premium = any(d in host for d in avm.PREMIUM_FETCH_DOMAINS)
        precio: Optional[float] = None
        confirmado = False
        if es_premium and verificados < MAX_VERIFICAR_PRECIO:
            verificados += 1
            precio, confirmado = await _verificar_precio(url, req)
            if confirmado and not _dentro_de_rango(precio, req):
                continue  # precio confirmado y fuera de rango: se descarta
        resultados.append({
            "titulo": item.get("title") or "",
            "url": url,
            "portal": item.get("portal") or avm._portal_name(url),
            "precio": precio,
            "precio_confirmado": confirmado,
            "snippet": (item.get("snippet") or "")[:400],
        })

    resultados.sort(key=lambda r: (not r["precio_confirmado"]))
    resultados = resultados[:MAX_RESULTADOS_GUARDADOS]

    ahora = datetime.now(timezone.utc).isoformat()
    try:
        await delete_rows("busqueda_resultados", {"requerimiento_id": f"eq.{req['id']}"})
    except Exception as exc:
        log.warning("No se pudo limpiar resultados previos de %s: %s", req.get("id"), exc)
    if resultados:
        filas = [{
            "requerimiento_id": req["id"], "user_id": req["user_id"], "contacto_id": req["contacto_id"],
            "titulo": r["titulo"], "url": r["url"], "portal": r["portal"], "precio": r["precio"],
            "precio_confirmado": r["precio_confirmado"], "snippet": r["snippet"], "encontrado_en": ahora,
        } for r in resultados]
        try:
            await post_rows("busqueda_resultados", filas, prefer="return=minimal")
        except Exception as exc:
            log.warning("No se pudieron guardar resultados de %s: %s", req.get("id"), exc)
    try:
        await patch_rows("requerimientos_busqueda", {"id": f"eq.{req['id']}"}, {"ultima_busqueda_en": ahora})
    except Exception as exc:
        log.warning("No se pudo marcar ultima_busqueda_en de %s: %s", req.get("id"), exc)
    return len(resultados)


async def _escanear_y_loguear(req: Dict[str, Any]) -> None:
    try:
        n = await _escanear_requerimiento(req)
        log.info("Escaneo inmediato para contacto %s: %d resultados", req.get("contacto_id"), n)
    except Exception as exc:
        log.warning("Fallo el escaneo inmediato para contacto %s: %s", req.get("contacto_id"), exc)


# ── Endpoints ────────────────────────────────────────────────────────────

class RequerimientoIn(BaseModel):
    activo: bool = True
    operacion: str = "venta"
    tipo_inmueble: str = "casa"
    colonia: str = ""
    ciudad: str = ""
    estado: str = ""
    precio_min: float = 0
    precio_max: float = 0
    recamaras_min: int = 0
    notas: str = ""


@router.get("/api/buscador/requerimiento/{contacto_id}")
async def obtener_requerimiento(contacto_id: str, request: Request):
    uid = await require_user_id(request, detail="Inicia sesión para continuar.")
    _require_db()
    await _verificar_contacto(contacto_id, uid)
    filas = await get_rows("requerimientos_busqueda", {
        "contacto_id": f"eq.{contacto_id}", "user_id": f"eq.{uid}", "select": "*", "limit": "1",
    })
    return filas[0] if filas else {}


@router.put("/api/buscador/requerimiento/{contacto_id}")
async def guardar_requerimiento(contacto_id: str, body: RequerimientoIn, request: Request):
    uid = await require_user_id(request, detail="Inicia sesión para continuar.")
    _require_db()
    await _verificar_contacto(contacto_id, uid)

    ahora = datetime.now(timezone.utc).isoformat()
    fila = {
        "user_id": uid,
        "contacto_id": contacto_id,
        "activo": body.activo,
        "operacion": body.operacion,
        "tipo_inmueble": body.tipo_inmueble,
        "colonia": body.colonia.strip() or None,
        "ciudad": body.ciudad.strip() or None,
        "estado": body.estado.strip() or None,
        "precio_min": body.precio_min or None,
        "precio_max": body.precio_max or None,
        "recamaras_min": body.recamaras_min or None,
        "notas": body.notas.strip() or None,
        "actualizado_en": ahora,
    }
    try:
        guardadas = await upsert_rows("requerimientos_busqueda", [fila], conflict="contacto_id")
    except httpx.HTTPStatusError as exc:
        detalle = exc.response.text[:200] if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"No se pudo guardar el requerimiento: {detalle}")

    guardado = guardadas[0] if guardadas else fila
    if body.activo and body.colonia.strip():
        # No bloquea la respuesta: el usuario ve su requerimiento guardado
        # de inmediato y los primeros enlaces llegan segundos después, sin
        # tener que esperar a la corrida diaria del ciclo de fondo.
        asyncio.create_task(_escanear_y_loguear(guardado))
    return guardado


@router.get("/api/buscador/resultados/{contacto_id}")
async def obtener_resultados(contacto_id: str, request: Request):
    uid = await require_user_id(request, detail="Inicia sesión para continuar.")
    _require_db()
    await _verificar_contacto(contacto_id, uid)
    reqs = await get_rows("requerimientos_busqueda", {
        "contacto_id": f"eq.{contacto_id}", "user_id": f"eq.{uid}", "select": "*", "limit": "1",
    })
    resultados = await get_rows("busqueda_resultados", {
        "contacto_id": f"eq.{contacto_id}", "user_id": f"eq.{uid}", "select": "*",
        "order": "precio_confirmado.desc,encontrado_en.desc",
    })
    return {"requerimiento": reqs[0] if reqs else None, "resultados": resultados}


@router.post("/api/buscador/escanear/{contacto_id}")
async def escanear_ahora(contacto_id: str, request: Request):
    uid = await require_user_id(request, detail="Inicia sesión para continuar.")
    _require_db()
    await _verificar_contacto(contacto_id, uid)
    filas = await get_rows("requerimientos_busqueda", {
        "contacto_id": f"eq.{contacto_id}", "user_id": f"eq.{uid}", "select": "*", "limit": "1",
    })
    if not filas:
        raise HTTPException(status_code=404, detail="Este cliente no tiene un requerimiento guardado todavía.")
    req = filas[0]
    if not req.get("activo"):
        raise HTTPException(status_code=400, detail="El requerimiento está desactivado.")
    n = await _escanear_requerimiento(req)
    return {"ok": True, "resultados": n}


@router.get("/api/buscador")
async def listar_requerimientos(request: Request):
    uid = await require_user_id(request, detail="Inicia sesión para continuar.")
    _require_db()
    reqs = await get_rows("requerimientos_busqueda", {
        "user_id": f"eq.{uid}", "activo": "eq.true", "select": "*", "order": "actualizado_en.desc",
    })
    if not reqs:
        return []

    ids_contacto = ",".join(dict.fromkeys(r["contacto_id"] for r in reqs))
    contactos = await get_rows("contactos", {
        "id": f"in.({ids_contacto})", "user_id": f"eq.{uid}", "select": "id,nombre,telefono",
    })
    por_contacto = {c["id"]: c for c in contactos}

    ids_req = ",".join(dict.fromkeys(r["id"] for r in reqs))
    resultados = await get_rows("busqueda_resultados", {
        "requerimiento_id": f"in.({ids_req})", "user_id": f"eq.{uid}",
        "select": "requerimiento_id",
    })
    conteo: Dict[str, int] = {}
    for r in resultados:
        conteo[r["requerimiento_id"]] = conteo.get(r["requerimiento_id"], 0) + 1

    salida = []
    for r in reqs:
        c = por_contacto.get(r["contacto_id"], {})
        salida.append({
            **r,
            "cliente_nombre": c.get("nombre") or "Cliente",
            "total_resultados": conteo.get(r["id"], 0),
        })
    return salida


# ── Ciclo de fondo: una lectura diaria por requerimiento activo ───────────

async def _revisar_pendientes() -> None:
    limite = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    try:
        pendientes = await get_rows("requerimientos_busqueda", {
            "select": "*",
            "activo": "eq.true",
            "or": f"(ultima_busqueda_en.is.null,ultima_busqueda_en.lt.{limite})",
            "limit": "30",
        })
    except Exception as exc:
        log.warning("No se pudo leer requerimientos pendientes: %s", exc)
        return
    for req in pendientes:
        try:
            await _escanear_requerimiento(req)
        except Exception as exc:
            log.warning("Fallo escaneando requerimiento %s: %s", req.get("id"), exc)


async def _ciclo_buscador() -> None:
    while True:
        try:
            await _revisar_pendientes()
        except Exception as exc:
            log.error("Fallo el ciclo del buscador de propiedades: %s", exc)
        await asyncio.sleep(3600)


@router.on_event("startup")
async def _iniciar_ciclo_buscador() -> None:
    if not settings.buscador_propiedades_enabled:
        log.warning(
            "Ciclo del buscador de propiedades DESACTIVADO por "
            "BUSCADOR_PROPIEDADES_ACTIVO; no se escaneará ningún "
            "requerimiento desde esta instancia."
        )
        return
    asyncio.create_task(_ciclo_buscador())
