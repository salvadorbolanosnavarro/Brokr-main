"""Entrenar con datos reales: a demanda (botón "Entrenar ahora") o el día 1
de cada mes (jobs.mensual). Un solo entrenamiento a la vez.

Además de los cierres ligados a un anuncio, los cierres capturados a mano
(POST /avm/v2/cierre) se valúan con el modelo nuevo, que nunca los vio
(no son anuncios), y se comparan contra su precio real: así se mide la
precisión y se calibra el rango con ventas de verdad.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import registry
from . import settings as S

log = logging.getLogger("broquer.avm_v2.entrenamiento")
TZ_MX = timezone(timedelta(hours=-6))
MIN_ANUNCIOS = 300           # anuncios útiles (limpios, sin duplicados) para entrenar
MIN_ANUNCIOS_CIUDAD = 100    # por debajo, la ciudad se valúa con poca información
MIN_CIERRES_MEDIR = 10
MIN_CIERRES_CALIBRAR = 30

estado: dict = {"estado": "inactivo"}
_lock = asyncio.Lock()
_cache_resumen: dict = {}


def _segundos(desde: float) -> int:
    return int(time.monotonic() - desde)


async def resumen_datos(usar_cache: bool = True) -> dict:
    """Cuántos anuncios útiles y cierres hay por ciudad."""
    if usar_cache and _cache_resumen.get("t") and time.monotonic() - _cache_resumen["t"] < 600:
        return _cache_resumen["datos"]
    from .etl import repo
    from . import pipeline as P
    from .indice import IndicePrecios
    datos = await repo.cargar_todo()
    por_ciudad = {c["nombre"]: {"anuncios_utiles": 0, "anuncios_totales": 0, "cierres": 0} for c in S.ciudades()}
    utiles = 0
    if not datos["listings"].empty:
        lst = datos["listings"]
        for ciudad, n in lst.groupby("ciudad").size().items():
            por_ciudad.setdefault(ciudad, {"anuncios_utiles": 0, "anuncios_totales": 0, "cierres": 0})
            por_ciudad[ciudad]["anuncios_totales"] = int(n)
        base, _ = await asyncio.to_thread(P.preparar_base, lst, IndicePrecios(datos["indice"]),
                                          pd.Timestamp(datetime.now(TZ_MX).date()))
        utiles = int(len(base))
        for ciudad, n in base.groupby("ciudad").size().items():
            por_ciudad[ciudad]["anuncios_utiles"] = int(n)
    if not datos["closings"].empty:
        for ciudad, n in datos["closings"].groupby("municipio").size().items():
            por_ciudad.setdefault(ciudad, {"anuncios_utiles": 0, "anuncios_totales": 0, "cierres": 0})
            por_ciudad[ciudad]["cierres"] = int(n)
    out = {"ciudades": por_ciudad, "anuncios_utiles": utiles, "cierres": int(len(datos["closings"])),
           "minimo_para_entrenar": MIN_ANUNCIOS, "minimo_por_ciudad": MIN_ANUNCIOS_CIUDAD,
           "minimo_cierres_calibrar": MIN_CIERRES_CALIBRAR}
    _cache_resumen.update({"t": time.monotonic(), "datos": out})
    return out


def evaluar_cierres_capturados(modelo, cierres: pd.DataFrame) -> pd.DataFrame:
    """Valúa cada cierre capturado (con ubicación y m²) con el modelo y lo
    compara con su precio real. δ de cada cierre se calcula sin ese cierre."""
    from .ensemble import TablaDelta
    from .indice import IndicePrecios
    if cierres is None or cierres.empty:
        return pd.DataFrame()
    c = cierres.copy()
    for col in ("lat", "lon", "m2_construidos", "m2_terreno", "precio_cierre", "precio_oferta_inicial",
                "recamaras", "banos", "edad_anios", "conservacion"):
        if col in c:
            c[col] = pd.to_numeric(c[col], errors="coerce")
    c = c[c["lat"].notna() & c["lon"].notna()]
    c = c[np.where(c["tipo"] == "terreno", c.get("m2_terreno", np.nan), c.get("m2_construidos", np.nan)) > 0]
    if c.empty:
        return pd.DataFrame()
    indice = modelo.indice if isinstance(modelo.indice, IndicePrecios) else IndicePrecios()
    delta_original = modelo.delta
    filas = []
    try:
        for i, r in c.reset_index(drop=True).iterrows():
            otros = c.drop(index=c.index[i])
            modelo.delta = TablaDelta.desde_cierres(otros)
            sujeto = {k: (None if pd.isna(r.get(k)) else r.get(k)) for k in
                      ("tipo", "lat", "lon", "m2_construidos", "m2_terreno", "recamaras", "banos", "edad_anios",
                       "conservacion", "colonia")}
            sujeto["municipio"] = r.get("municipio")
            res = modelo.estimar(sujeto)
            f_t = indice.factor(r.get("municipio") or "", pd.Timestamp(r["fecha_cierre"]), modelo.fecha_valuacion)
            real = float(r["precio_cierre"]) * f_t
            filas.append({
                "id": r.get("id"), "ciudad": res["ciudad"], "tipo": r["tipo"], "segmento": S.segmento(real),
                "real": real, "real_aj": real, "estimado": res["valor"], "emitido": res["emitido"],
                "bajo": res["rango"][0] if res["rango"] else None, "alto": res["rango"][1] if res["rango"] else None,
                "confianza": res["confianza"], "ens_valor_calc": res["_valor_calc"], "ens_escala": res["_escala"],
            })
    finally:
        modelo.delta = delta_original
    return pd.DataFrame(filas)


async def entrenar_con_datos_reales(origen: str = "manual") -> dict:
    """Entrena, mide y, si no es peor que el modelo actual, lo pone en uso."""
    from . import pipeline as P
    from .ensemble import ConformalMondrian
    from .etl import repo
    from .eval import validate as V
    from .eval.metrics import metricas
    from .service import servicio
    if _lock.locked():
        return {"ok": False, "motivo": "Ya hay un entrenamiento en curso."}
    async with _lock:
        t0 = time.monotonic()
        estado.clear()
        estado.update({"estado": "entrenando", "paso": "Leyendo anuncios y cierres", "origen": origen,
                       "inicio": datetime.now(timezone.utc).isoformat()})
        try:
            resumen = await resumen_datos(usar_cache=False)
            if resumen["anuncios_utiles"] < MIN_ANUNCIOS:
                estado.update({"estado": "insuficiente", "fin": datetime.now(timezone.utc).isoformat(),
                               "motivo": f"Hay {resumen['anuncios_utiles']} anuncios útiles; se necesitan "
                                         f"{MIN_ANUNCIOS}."})
                return {"ok": False, **estado}
            datos = await repo.cargar_todo()
            fv = pd.Timestamp(datetime.now(TZ_MX).date())
            estado["paso"] = "Entrenando los tres motores y validando"
            modelo, extra = await asyncio.to_thread(P.entrenar, datos["listings"], datos["closings"],
                                                    datos["indice"], fv, "reales", datos["contexto"])
            estado["paso"] = "Midiendo contra cierres reales"
            capt = await asyncio.to_thread(evaluar_cierres_capturados, modelo, datos["closings"])
            if len(capt) >= MIN_CIERRES_MEDIR:
                met = metricas(capt["estimado"], capt["real"], capt["bajo"], capt["alto"], capt["emitido"])
                met["fuente_medicion"] = f"{len(capt)} cierres capturados"
            else:
                cc = await asyncio.to_thread(V.contra_cierres, datos["listings"], datos["closings"], datos["indice"],
                                             fv, datos["contexto"])
                if cc is not None and len(cc) >= MIN_CIERRES_MEDIR:
                    met = V.resumen(cc)["global"]
                    met["fuente_medicion"] = f"{len(cc)} cierres ligados a anuncios"
                else:
                    h = await asyncio.to_thread(V.holdout_temporal, datos["listings"], datos["closings"],
                                                datos["indice"], fv, datos["contexto"])
                    met = V.resumen(h["oferta"])["global"] if V.resumen(h["oferta"]) else {}
                    met["fuente_medicion"] = "anuncios de los últimos 3 meses (aún sin cierres suficientes)"
            if len(capt) >= MIN_CIERRES_CALIBRAR:
                # Rango calibrado con ventas reales (lo medido arriba usó el
                # rango anterior, así que la cobertura reportada es honesta).
                ok = capt[capt["ens_valor_calc"].notna()]
                modelo.conformal = ConformalMondrian().ajustar(
                    np.log(ok["real"]), np.log(ok["ens_valor_calc"]), ok["ens_escala"], ok["ciudad"], ok["segmento"])
                met["rango_calibrado_con"] = f"{len(ok)} cierres capturados"
            met["anuncios_utiles"] = resumen["anuncios_utiles"]
            met = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in met.items()}
            actual = servicio.metricas if getattr(servicio.modelo, "datos", None) == "reales" else None
            promover, motivo = registry.decidir_promocion(met, actual, S.PROMOCION_MAX_EMPEORA_PTS)
            estado["paso"] = "Guardando el modelo"
            await asyncio.to_thread(registry.guardar_local, modelo, met)
            await registry.subir(modelo, met)
            if promover:
                registry.apuntar_local(modelo.version, met)
                await registry.promover_remoto(modelo.version, met)
                servicio.reemplazar(modelo, met)
            _cache_resumen.clear()
            estado.update({"estado": "listo", "paso": None, "fin": datetime.now(timezone.utc).isoformat(),
                           "segundos": _segundos(t0), "version": modelo.version, "promovido": promover,
                           "motivo": motivo, "metricas": met})
            log.info("Entrenamiento %s: %s (%s)", modelo.version, "promovido" if promover else "NO promovido", motivo)
            return {"ok": True, **estado}
        except Exception as exc:
            log.exception("Entrenamiento falló: %s", exc)
            estado.update({"estado": "error", "paso": None, "fin": datetime.now(timezone.utc).isoformat(),
                           "motivo": "El entrenamiento falló; revisa los logs de Railway."})
            return {"ok": False, **estado}
