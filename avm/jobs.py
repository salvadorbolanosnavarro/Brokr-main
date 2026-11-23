"""Trabajos programados del AVM v2 (solo si AVM_V2_JOBS=true, en UNA instancia).

- Diario 03:00 (hora de México): ingesta de anuncios + limpieza + duplicados.
- Semanal (lunes 04:00): recalibración de δ (oferta→cierre) y del rango conformal.
- Mensual (día 1, 05:00): reentrenamiento del Motor B con reporte; si el MdAPE
  empeora más de 2 puntos, NO se promueve y se queda el modelo anterior.

Mismo patrón que el ciclo de recordatorios del repo: un loop asyncio que
despierta cada 15 minutos y revisa qué toca. Cada corrida deja su fecha en
Storage/disco para no repetirse si Railway reinicia la instancia.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from core.config import settings

from . import registry
from . import settings as S

log = logging.getLogger("broquer.avm_v2.jobs")
TZ_MX = timezone(timedelta(hours=-6))
ESTADO = "jobs_estado.json"


def _estado() -> dict:
    p = registry._dir() / ESTADO
    return json.loads(p.read_text()) if p.exists() else {}


def _marcar(nombre: str, cuando: datetime) -> None:
    e = _estado()
    e[nombre] = cuando.date().isoformat()
    (registry._dir() / ESTADO).write_text(json.dumps(e))


def toca(nombre: str, ahora: datetime, estado: dict) -> bool:
    """Lógica pura (probada): ¿corresponde correr este trabajo ahora?"""
    hoy = ahora.date().isoformat()
    if estado.get(nombre) == hoy:
        return False
    if nombre == "diario":
        return ahora.hour >= 3
    if nombre == "semanal":
        return ahora.weekday() == 0 and ahora.hour >= 4
    if nombre == "mensual":
        return ahora.day == 1 and ahora.hour >= 5
    return False


async def diario() -> dict:
    from .etl import extract_text, ingest_listings
    res = await ingest_listings.correr()
    res["texto"] = await extract_text.correr()
    return res


async def semanal() -> dict:
    """Recalibra δ y conformal sobre el modelo actual sin reentrenar motores."""
    from . import pipeline as P
    from .etl import repo
    from .service import servicio
    if servicio.modelo is None:
        return {"omitido": "sin modelo"}
    datos = await repo.cargar_todo()
    modelo = servicio.modelo
    from .ensemble import TablaDelta
    modelo.delta = TablaDelta.desde_cierres(datos["closings"])
    base = modelo.referencia
    oof = await asyncio.to_thread(P.predecir_oof, base, S.B_ROUNDS)
    modelo.sigma = P.sigma_desde_oof(oof)
    oof_ens = P.ensamblar_oof(oof, modelo.sigma, modelo.delta, None, aplicar_delta=False)
    c_eval = P.evaluar_cierres_oof(oof, datos["closings"], base, modelo.indice, modelo.fecha_valuacion, modelo.sigma)
    modelo.conformal = P.calibrar_conformal(oof_ens, c_eval)
    registry.guardar_local(modelo, servicio.metricas)
    await registry.subir(modelo, servicio.metricas)
    return {"delta_celdas": len(modelo.delta.filas), "conformal_grupos": len(modelo.conformal.q)}


async def mensual() -> dict:
    from . import pipeline as P
    from .etl import repo
    from .eval import run_report, validate as V
    from .service import servicio
    datos = await repo.cargar_todo()
    if datos["listings"].empty:
        return {"omitido": "sin anuncios"}
    fv = pd.Timestamp(datetime.now(TZ_MX).date())
    modelo, _ = await asyncio.to_thread(P.entrenar, datos["listings"], datos["closings"], datos["indice"], fv,
                                        "reales", datos["contexto"])
    cc = await asyncio.to_thread(V.contra_cierres, datos["listings"], datos["closings"], datos["indice"], fv,
                                 datos["contexto"])
    if cc is None:   # sin cierres: se mide contra el hold-out temporal de oferta
        h = await asyncio.to_thread(V.holdout_temporal, datos["listings"], datos["closings"], datos["indice"], fv,
                                    datos["contexto"])
        met = V.resumen(h["oferta"])["global"]
    else:
        met = V.resumen(cc)["global"]
    promover, motivo = registry.decidir_promocion(met, servicio.metricas, S.PROMOCION_MAX_EMPEORA_PTS)
    registry.guardar_local(modelo, met)
    await registry.subir(modelo, met)
    if promover:
        registry.apuntar_local(modelo.version, met)
        await registry.promover_remoto(modelo.version, met)
        servicio.reemplazar(modelo, met)
    await asyncio.to_thread(run_report.escribir, datos["listings"], datos["closings"], datos["indice"], fv, "reales",
                            datos["contexto"], S.B_ROUNDS, modelo)
    log.info("Reentreno mensual %s: %s (%s)", modelo.version, "promovido" if promover else "NO promovido", motivo)
    return {"version": modelo.version, "promovido": promover, "motivo": motivo, "metricas": met}


TRABAJOS = {"diario": diario, "semanal": semanal, "mensual": mensual}


async def ciclo() -> None:
    while True:
        ahora = datetime.now(TZ_MX)
        estado = _estado()
        for nombre, fn in TRABAJOS.items():
            if toca(nombre, ahora, estado):
                try:
                    res = await fn()
                    log.info("AVM v2 job %s: %s", nombre, res)
                except Exception as exc:
                    log.exception("AVM v2 job %s falló: %s", nombre, exc)
                _marcar(nombre, ahora)
        await asyncio.sleep(15 * 60)


def arrancar() -> asyncio.Task | None:
    if not settings.avm_v2_jobs:
        return None
    return asyncio.create_task(ciclo())
