"""AVM Broquer v2.

POST /avm/v2/estimar   valor, rango, confianza, desglose por motor, comparables,
                       explicación y versión (requiere sesión).
POST /avm/v2/cierre    captura un cierre real → avm_closings (requiere sesión).
GET  /avm/v2/estado    si la vista nueva está activa y qué modelo está cargado.

Se emite como "Opinión Comercial de Valor", nunca como avalúo.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from core.auth import require_user_id
from core.config import settings

log = logging.getLogger("broquer.avm_v2")
router = APIRouter(prefix="/avm/v2", tags=["avm-v2"])

# El modelo (lightgbm, pandas, h3…) se importa al primer uso, no al montar el
# router: así los endpoints existen aunque falte alguna dependencia y el resto
# del backend arranca igual de rápido.


def _servicio():
    from avm.service import servicio
    return servicio


def _repo():
    from avm.etl import repo
    return repo


MSG_AMPLIA = "Esa dirección solo ubica la ciudad. Escribe al menos la colonia (mejor calle y número) o elige una sugerencia."


async def geocodificar(direccion: str):
    """None si no se encontró; 'amplia' si solo se ubicó la ciudad."""
    from avm.service import UbicacionAmplia, geocodificar as _g
    try:
        return await _g(direccion)
    except UbicacionAmplia:
        return "amplia"


class Amenidades(BaseModel):
    alberca: bool = False
    jardin: bool = False
    roof_garden: bool = False
    seguridad_24h: bool = False
    esquina: bool = False
    remodelada: bool = False
    cajones: Optional[int] = Field(None, ge=0, le=20)
    regimen: Optional[Literal["condominio", "privada", "independiente", "ejidal"]] = None


class EstimarRequest(BaseModel):
    direccion: Optional[str] = Field(None, max_length=300)
    lat: Optional[float] = Field(None, ge=14, le=33)
    lon: Optional[float] = Field(None, ge=-119, le=-86)
    colonia: Optional[str] = Field(None, max_length=120)
    tipo: Literal["casa", "depto", "terreno", "local"]
    m2_construidos: Optional[float] = Field(None, gt=0, le=20000)
    m2_terreno: Optional[float] = Field(None, gt=0, le=500000)
    recamaras: Optional[int] = Field(None, ge=0, le=20)
    banos: Optional[float] = Field(None, ge=0, le=20)
    edad_anios: Optional[float] = Field(None, ge=0, le=150)
    conservacion: Optional[int] = Field(None, ge=1, le=5)
    calidad: Optional[Literal["economica", "media", "residencial", "residencial_plus"]] = None
    amenidades: Amenidades = Amenidades()

    @model_validator(mode="after")
    def _ubicacion_y_superficie(self):
        if (self.lat is None or self.lon is None) and not self.direccion:
            raise ValueError("Indica la dirección o las coordenadas.")
        if self.tipo == "terreno" and not self.m2_terreno:
            raise ValueError("Para terreno indica los m² de terreno.")
        if self.tipo != "terreno" and not self.m2_construidos:
            raise ValueError("Indica los m² de construcción.")
        return self


class CierreRequest(BaseModel):
    tipo: Literal["casa", "depto", "terreno", "local"]
    precio_cierre: float = Field(gt=0)
    precio_oferta_inicial: Optional[float] = Field(None, gt=0)
    fecha_cierre: date
    dias_en_mercado: Optional[int] = Field(None, ge=0, le=3650)
    fuente: Literal["navarro", "cierres", "avaluo"] = "cierres"
    listing_id: Optional[int] = None
    m2_construidos: Optional[float] = Field(None, gt=0)
    m2_terreno: Optional[float] = Field(None, gt=0)
    recamaras: Optional[int] = Field(None, ge=0, le=20)
    banos: Optional[float] = Field(None, ge=0, le=20)
    edad_anios: Optional[float] = Field(None, ge=0, le=150)
    conservacion: Optional[int] = Field(None, ge=1, le=5)
    direccion: Optional[str] = Field(None, max_length=300)
    lat: Optional[float] = Field(None, ge=14, le=33)
    lon: Optional[float] = Field(None, ge=-119, le=-86)
    municipio: Optional[str] = Field(None, max_length=120)
    colonia: Optional[str] = Field(None, max_length=120)
    notas: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _ubicacion(self):
        if (self.lat is None or self.lon is None) and not self.direccion and not self.municipio:
            raise ValueError("Indica la dirección del inmueble vendido.")
        if self.tipo == "terreno" and not self.m2_terreno:
            raise ValueError("Para terreno indica los m² de terreno.")
        if self.tipo != "terreno" and not self.m2_construidos:
            raise ValueError("Indica los m² de construcción.")
        return self


@router.get("/estado")
async def estado():
    """Público a propósito: el front lo usa para decidir si muestra la vista
    nueva. No expone datos, solo el flag y la versión del modelo."""
    try:
        info = _servicio().info()
    except Exception as exc:      # dependencias del modelo ausentes
        info = {"estado": "no_disponible", "detalle": str(exc)[:120]}
    from core.legacy_main_config import legacy_main_settings
    # Solo sí/no: qué fuentes de datos reales están listas (nunca las llaves).
    fuentes = {
        "ubicacion_google": bool(settings.google_places_key),
        "anuncios_firecrawl": bool(legacy_main_settings.firecrawl_api_key),
        "lectura_descripciones": bool(settings.groq_api_key or settings.anthropic_api_key),
        "recoleccion_diaria": bool(settings.avm_v2_jobs),
    }
    return {"activo": settings.avm_v2_enabled, **info, "fuentes": fuentes}


@router.post("/estimar")
async def estimar(req: EstimarRequest, request: Request):
    user_id = await require_user_id(request)
    try:
        servicio = _servicio()
    except Exception:
        raise HTTPException(503, "El AVM v2 no está disponible en este servidor.") from None
    if servicio.modelo is None:
        await servicio.cargar()
    if servicio.modelo is None:
        raise HTTPException(503, "El modelo v2 todavía no está entrenado. Usa la opinión de valor actual mientras tanto.")
    lat, lon, precision = req.lat, req.lon, "exacta"
    if lat is None or lon is None:
        geo = await geocodificar(req.direccion or "")
        if geo == "amplia":
            raise HTTPException(422, MSG_AMPLIA)
        if not geo:
            raise HTTPException(422, "No pude ubicar esa dirección. Prueba con calle, número, colonia y ciudad.")
        lat, lon, precision = geo
    a = req.amenidades
    sujeto = {
        "tipo": req.tipo, "lat": lat, "lon": lon, "colonia": req.colonia,
        "m2_construidos": req.m2_construidos, "m2_terreno": req.m2_terreno,
        "recamaras": req.recamaras, "banos": req.banos, "edad_anios": req.edad_anios,
        "conservacion": req.conservacion, "calidad_construccion": req.calidad,
        "alberca": float(a.alberca), "jardin": float(a.jardin), "roof_garden": float(a.roof_garden),
        "seguridad_24h": float(a.seguridad_24h), "esquina": float(a.esquina), "remodelada": float(a.remodelada),
        "cajones": a.cajones, "regimen": a.regimen,
    }
    try:
        resultado = await asyncio.to_thread(servicio.estimar, sujeto)
    except Exception as exc:
        log.exception("AVM v2 falló: %s", exc)
        raise HTTPException(500, "No se pudo calcular la estimación.") from None
    if precision == "aproximada":
        resultado["advertencias"].append("La dirección se ubicó de forma aproximada (centro de colonia o calle).")
    resultado["ubicacion"] = {"lat": round(lat, 6), "lon": round(lon, 6), "precision": precision}
    asyncio.create_task(_bitacora(user_id, req.model_dump(mode="json"), resultado))
    return resultado


async def _bitacora(user_id: str, entrada: dict, r: dict) -> None:
    """avm_predictions: cada estimado queda auditado para medirlo contra cierres."""
    try:
        await _repo().guardar_prediccion({
            "usuario": user_id, "version_modelo": r["version"], "entrada": entrada,
            "motores": r["motores"], "pesos": {k: m["peso"] for k, m in r["motores"].items()},
            "valor": r["valor"], "rango_bajo": r["rango"][0] if r["rango"] else None,
            "rango_alto": r["rango"][1] if r["rango"] else None, "confianza": r["confianza"],
            "delta": r["descuento_negociacion_pct"] / 100, "emitido": r["emitido"],
        })
    except Exception as exc:     # la bitácora nunca debe tumbar la respuesta
        log.warning("No se guardó la bitácora del AVM v2: %s", exc)


@router.post("/cierre")
async def capturar_cierre(req: CierreRequest, request: Request):
    user_id = await require_user_id(request)
    fila = req.model_dump(mode="json", exclude_none=True)
    fila.pop("direccion", None)
    if (req.lat is None or req.lon is None) and req.direccion:
        geo = await geocodificar(req.direccion)
        if geo and geo != "amplia":
            fila["lat"], fila["lon"] = geo[0], geo[1]
    if not fila.get("municipio") and fila.get("lat") is not None:
        try:
            from avm.contexto import ciudad_mas_cercana
            fila["municipio"] = ciudad_mas_cercana(fila["lat"], fila["lon"])
        except Exception:
            pass
    fila["capturado_por"] = user_id
    try:
        guardado = await _repo().guardar_cierre(fila)
    except Exception as exc:
        log.warning("No se guardó el cierre: %s", exc)
        raise HTTPException(500, "No se pudo guardar el cierre. ¿Ya se corrió migracion-avm-v2.sql?") from None
    from avm.settings import segmento
    try:
        from avm import entrenamiento
        entrenamiento._cache_resumen.clear()
    except Exception:
        pass
    seg = segmento(req.precio_cierre)
    descuento = None
    if req.precio_oferta_inicial:
        descuento = round(100 * (1 - req.precio_cierre / req.precio_oferta_inicial), 1)
    return {"ok": True, "id": guardado.get("id"), "segmento": seg, "descuento_pct": descuento}


async def _es_admin(request: Request) -> bool:
    from core.admin import require_admin
    try:
        await require_admin(request)
        return True
    except HTTPException:
        return False


@router.get("/datos")
async def datos(request: Request):
    """Cuántos anuncios útiles y cierres hay por ciudad, si alcanza para
    entrenar con datos reales y cómo va el último entrenamiento."""
    await require_user_id(request)
    try:
        from avm import entrenamiento
        resumen = await entrenamiento.resumen_datos()
    except Exception as exc:
        log.warning("Resumen de datos AVM v2 falló: %s", exc)
        raise HTTPException(503, "No se pudieron leer los datos del modelo.") from None
    return {**resumen, "es_admin": await _es_admin(request), "entrenamiento": dict(entrenamiento.estado),
            "modelo": _servicio().info()}


@router.post("/entrenar")
async def entrenar(request: Request):
    """Solo administradores. Arranca el entrenamiento con datos reales en
    segundo plano (tarda minutos); el avance se consulta en GET /avm/v2/entrenar."""
    from core.admin import require_admin
    await require_admin(request)
    from avm import entrenamiento
    if entrenamiento.estado.get("estado") == "entrenando":
        raise HTTPException(409, "Ya hay un entrenamiento en curso.")
    resumen = await entrenamiento.resumen_datos(usar_cache=False)
    if resumen["anuncios_utiles"] < entrenamiento.MIN_ANUNCIOS:
        raise HTTPException(409, f"Todavía hay {resumen['anuncios_utiles']} anuncios útiles; se necesitan "
                                 f"{entrenamiento.MIN_ANUNCIOS}. Deja correr la recolección diaria unos días más.")
    asyncio.create_task(entrenamiento.entrenar_con_datos_reales(origen="manual"))
    return {"iniciado": True}


@router.get("/entrenar")
async def estado_entrenamiento(request: Request):
    await require_user_id(request)
    from avm import entrenamiento
    return dict(entrenamiento.estado)


@router.on_event("startup")
async def _arranque() -> None:
    """Carga el modelo en memoria al arrancar (respuesta < 3 s) y, solo si
    AVM_V2_JOBS=true, arranca los trabajos programados en esta instancia.
    Si AVM_V2 está apagado y no hay jobs, no carga nada (producción intacta)."""
    if not (settings.avm_v2_enabled or settings.avm_v2_jobs):
        return
    try:
        from avm import jobs
    except Exception as exc:
        log.warning("AVM v2 sin dependencias del modelo: %s", exc)
        return

    async def _cargar():
        try:
            await _servicio().cargar()
        except Exception as exc:
            log.warning("AVM v2 no pudo cargar modelo al arrancar: %s", exc)

    asyncio.create_task(_cargar())
    jobs.arrancar()
