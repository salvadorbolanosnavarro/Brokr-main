"""Banxico SIE endpoints for INPC and UDIS."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import time

import httpx
from fastapi import APIRouter, HTTPException

from core.config import settings


router = APIRouter()

BANXICO_TOKEN = settings.banxico_token
BANXICO_BASE = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
BANXICO_SERIE_UDIS = settings.banxico_series_udis
BANXICO_SERIE_INPC = settings.banxico_series_inpc

_cache: dict = {}
_cache_ttl: dict = {}
CACHE_TTL = 21600


def cache_get(key):
    if key in _cache:
        data, ts = _cache[key]
        ttl = _cache_ttl.get(key, CACHE_TTL)
        if time.time() - ts < ttl:
            return data
        del _cache[key]
        _cache_ttl.pop(key, None)
    return None


def cache_set(key, data, ttl=None):
    _cache[key] = (data, time.time())
    if ttl is not None:
        _cache_ttl[key] = ttl


async def _banxico_fetch(serie: str, fecha_ini: str = None, fecha_fin: str = None) -> list:
    """Consulta una serie de Banxico SIE y devuelve únicamente datos publicados."""
    if not BANXICO_TOKEN:
        raise HTTPException(status_code=503, detail="BANXICO_TOKEN no configurado en el backend")
    if fecha_ini and fecha_fin:
        url = f"{BANXICO_BASE}/{serie}/datos/{fecha_ini}/{fecha_fin}"
    else:
        url = f"{BANXICO_BASE}/{serie}/datos/oportuno"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(
                url,
                params={"token": BANXICO_TOKEN},
                headers={"Accept": "application/json"},
            )
            if response.status_code in (401, 403):
                raise HTTPException(status_code=502, detail="Token Banxico rechazado")
            if response.status_code == 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"Banxico rechazó request: {response.text[:200]}",
                )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Banxico devolvió HTTP {response.status_code}",
                )
            data = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Error consultando Banxico: {exc}")

    series = (data.get("bmx") or {}).get("series") or []
    if not series:
        return []
    datos = series[0].get("datos") or []
    return [d for d in datos if d.get("dato") and d["dato"] != "N/E"]


@router.get("/api/inpc/{anio}/{mes}")
async def api_inpc(anio: int, mes: int):
    if not (1969 <= anio <= 2099):
        raise HTTPException(status_code=400, detail="Año fuera de rango (1969-2099)")
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mes debe ser 1-12")

    key = f"inpc:{anio}-{mes:02d}"
    cached = cache_get(key)
    if cached:
        return cached

    if mes == 12:
        last_day = 31
    else:
        last_day = (date(anio, mes + 1, 1) - timedelta(days=1)).day
    fecha_ini = f"{anio}-{mes:02d}-01"
    fecha_fin = f"{anio}-{mes:02d}-{last_day:02d}"
    datos = await _banxico_fetch(BANXICO_SERIE_INPC, fecha_ini, fecha_fin)

    fallback = False
    anio_real, mes_real = anio, mes
    if not datos:
        for _ in range(3):
            mes_real -= 1
            if mes_real < 1:
                mes_real = 12
                anio_real -= 1
            if mes_real == 12:
                ld = 31
            else:
                ld = (date(anio_real, mes_real + 1, 1) - timedelta(days=1)).day
            datos = await _banxico_fetch(
                BANXICO_SERIE_INPC,
                f"{anio_real}-{mes_real:02d}-01",
                f"{anio_real}-{mes_real:02d}-{ld:02d}",
            )
            if datos:
                fallback = True
                break
    if not datos:
        raise HTTPException(status_code=404, detail=f"INPC no publicado para {anio}-{mes:02d}")

    valor = float(str(datos[-1]["dato"]).replace(",", ""))
    fecha_pub = datos[-1]["fecha"]
    result = {
        "anio": anio_real,
        "mes": mes_real,
        "valor": valor,
        "fecha_publicacion": fecha_pub,
        "fuente": "banxico_sie",
        "fallback": fallback,
        "anio_solicitado": anio,
        "mes_solicitado": mes,
    }
    now = datetime.now()
    is_past = (anio < now.year) or (anio == now.year and mes < now.month)
    cache_set(
        key,
        result,
        ttl=6 * 3600 if fallback else (30 * 86400 if is_past else 6 * 3600),
    )
    return result


@router.get("/api/udis/{fecha}")
async def api_udis(fecha: str):
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha debe ser YYYY-MM-DD")

    key = f"udis:{fecha}"
    cached = cache_get(key)
    if cached:
        return cached

    datos = await _banxico_fetch(BANXICO_SERIE_UDIS, fecha, fecha)
    if not datos:
        fecha_ini = (fecha_obj - timedelta(days=14)).isoformat()
        datos = await _banxico_fetch(BANXICO_SERIE_UDIS, fecha_ini, fecha)
    if not datos:
        raise HTTPException(status_code=404, detail=f"UDIS no publicadas para {fecha}")

    valor = float(str(datos[-1]["dato"]).replace(",", ""))
    fecha_pub = datos[-1]["fecha"]
    result = {
        "fecha": fecha,
        "valor": valor,
        "fecha_publicacion": fecha_pub,
        "fuente": "banxico_sie",
    }
    is_past = fecha_obj < datetime.now().date()
    cache_set(key, result, ttl=7 * 86400 if is_past else 12 * 3600)
    return result
